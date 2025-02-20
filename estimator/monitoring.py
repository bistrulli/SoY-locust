from pathlib import Path
from config import locustDataDir,serviceName
import pandas as pd
import numpy as np
import docker
from prometheus_api_client import PrometheusConnect
import yaml
import pandas as pd
import requests_unixsocket  # Assicurati di avere requests_unixsocket installato (pip install requests-unixsocket)

class Monitoring:
    def __init__(self, window, sla, reducer=lambda x: sum(x)/len(x),
                 serviceName="",promHost="localhost",promPort=9090,sysfile=""):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.serviceName = serviceName
        self.promPort = promPort
        self.promHost = promHost
        self.sysfile = sysfile
        self.client = docker.from_env()
        if(not Path(self.sysfile).exists()):
            raise FileNotFoundError(f"File {self.sysfile} not found")
        self.sys=yaml.safe_load(self.sysfile.open())
        self.prom = PrometheusConnect(url=f"http://{self.promHost}:{self.promPort}", disable_ssl=True)
        self.reset()

    def tick(self, t):
        self.time+=[t]
        self.rts+=[self.getResponseTime()]
        self.tr+=[self.getTroughput()]
        self.cores+=[self.getCores()]
        self.replica+=[self.get_replicas(self.serviceName)]
        self.users+=[self.getUsers()]
        
        totRes=self.getTotalUtilization()
        self.memory+=[totRes["total_mem"]]
        self.util+=[totRes["total_cpu"]]

    def getUsers(self):
        #torno il numero di utenti attivi (Little's Law)
        return self.rts[-1]*self.tr[-1]

    def getCores(self):
        # Estrae il valore dell'attributo "cpus" dalla configurazione YAML per il servizio node
        cpus_str = self.sys.get("services", {}) \
                           .get("node", {}) \
                           .get("deploy", {}) \
                           .get("resources", {}) \
                           .get("limits", {}) \
                           .get("cpus", "0")
        try:
            return float(cpus_str)
        except ValueError:
            return 0.0

    # Funzione per eseguire una query su Prometheus
    def query_prometheus(self,metric_name):
        result = self.prom.custom_query(query=metric_name)
        return result

    def getResponseTime(self):
        """
        Calcola il tempo di risposta medio effettuando due query Prometheus:
        - locust_request_latency_seconds_sum
        - locust_request_latency_seconds_count
        Restituisce la latenza media (somma/count).
        """
        try:
            sum_result = self.prom.custom_query(query="locust_request_latency_seconds_sum")
            count_result = self.prom.custom_query(query="locust_request_latency_seconds_count")
            if sum_result and count_result:
                latency_sum = float(sum_result[0]['value'][1])
                latency_count = float(count_result[0]['value'][1])
                avg_latency = latency_sum / latency_count if latency_count > 0 else 0
                return avg_latency
            else:
                return 0
        except Exception as e:
            print("Error querying Prometheus for RT:", e)
            return 0

    def getTroughput(self):
        """
        Misura il numero di richieste al secondo utilizzando la metrica locust_requests_total.
        Viene eseguita una query Prometheus per ottenere il totale correntemente cumulativo, quindi
        se sono disponibili un valore e un timestamp precedenti, si calcola il delta richieste / delta tempo.
        """
        import time
        try:
            result = self.prom.custom_query(query="locust_requests_total")
            if result:
                current_total = float(result[0]['value'][1])
            else:
                current_total = 0
            current_time = time.time()
            if self.last_requests is None or self.last_timestamp is None:
                self.last_requests = current_total
                self.last_timestamp = current_time
                return 0
            dt = current_time - self.last_timestamp
            throughput = (current_total - self.last_requests) / dt if dt > 0 else 0
            self.last_requests = current_total
            self.last_timestamp = current_time
            return throughput
        except Exception as e:
            print("Error querying throughput from Prometheus:", e)
            return 0

    def getUtil(self):
        #logica per misurare l'utilizzo da docker
        pass

    def get_replicas(self,service_name):
        try:
            service = self.client.services.get(service_name)
            replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
            return replicas
        except docker.errors.NotFound:
            print(f"Service '{service_name}' not found.")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def getTotalUtilization(self):
        """
        Aggrega l'utilizzo CPU e memoria di tutti i container appartenenti al servizio, filtrandoli per label.
        """
        total_cpu = 0.0
        total_mem = 0
        try:
            # Filtra i container usando l'etichetta Swarm del servizio
            containers = self.client.containers.list(filters={"label": f"com.docker.swarm.service.name={self.serviceName}"})
            for container in containers:
                try:
                    stats = container.stats(stream=False)
                    cpu_usage = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                    mem_usage = stats.get("memory_stats", {}).get("usage", 0)
                    total_cpu += cpu_usage
                    total_mem += mem_usage
                except Exception as ex:
                    print(f"Error fetching stats for container {container.id}: {ex}")
            return {"total_cpu": total_cpu, "total_mem": total_mem}
        except Exception as e:
            print("Error in getTotalUtilization:", e)
            return {"total_cpu": 0, "total_mem": 0}

    def get_container_stats_rest(self, container_id):
        """
        Recupera le statistiche di un container usando le API REST di Docker.
        """
        session = requests_unixsocket.Session()
        url = f"http+unix://%2Fvar%2Frun%2Fdocker.sock/containers/{container_id}/stats?stream=false"
        try:
            response = session.get(url, timeout=1)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error: HTTP {response.status_code} for container {container_id}")
                return {}
        except Exception as ex:
            print(f"Error fetching stats (REST) for container {container_id}: {ex}")
            return {}

    def getTotalUtilization_via_rest(self):
        """
        Usa le API REST di Docker per aggregare l'utilizzo CPU e memoria di tutti i container
        appartenenti al servizio (filtrati per etichetta).
        """
        total_cpu = 0.0
        total_mem = 0
        try:
            containers = self.client.containers.list(filters={"label": f"com.docker.swarm.service.name={self.serviceName}"})
            for container in containers:
                stats = self.get_container_stats_rest(container.id)
                cpu_usage = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                mem_usage = stats.get("memory_stats", {}).get("usage", 0)
                total_cpu += cpu_usage
                total_mem += mem_usage
            return {"total_cpu": total_cpu, "total_mem": total_mem}
        except Exception as e:
            print("Error in getTotalUtilization_via_rest:", e)
            return {"total_cpu": 0, "total_mem": 0}

    def getViolations(self):
        def appendViolation(rts):
            if self.reducer(rts) > self.sla:
                return 1
            else:
                return 0
        second = int(self.time[0])
        violations = []
        rts = []
        
        for (t, rt) in zip(self.time, self.allRts):
            if int(t) != second:
                violations.append(appendViolation(rts))
                rts = []
                second = int(t)
            rts.append(rt)
        violations.append(appendViolation(rts))
        return sum(violations)
        
    def reset(self):
        self.cores = []
        self.rts = []
        self.tr = []
        self.users = []
        self.time = []
        self.replica = []
        self.util = []
        self.memory =[]
        # Aggiunta per il throughput
        self.last_requests = None
        self.last_timestamp = None

    def save_to_csv(self, filename):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cores": self.cores,
            "rts": self.rts,
            "tr": self.tr,
            "users": self.users,
            "replica": self.replica,
            "util":self.util,
            "mem":self.memory
        }
        print("###saving results##")
        try:
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
            print(f"Data saved to {filename}")
        except Exception as e:
            print(e)
            print((f"{len(self.cores)},{len(self.rts)}"
                   f"{len(self.tr)},{len(self.users)},{len(self.replica)}"))