from pathlib import Path
from config import locustDataDir,serviceName
import pandas as pd
import numpy as np
import docker
from prometheus_api_client import PrometheusConnect
import yaml

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
        if(not Path(self.sysfile).exists()):
            raise FileNotFoundError(f"File {self.sysfile} not found")
        self.sys=yaml.safe_load(self.sysfile.open())
        self.prom = PrometheusConnect(url=f"http://{self.promHost}:{self.promPort}", disable_ssl=True)
        self.reset()

    def tick(self, t):
        for i in range(1, len(self.time)+1):
            if t - self.time[-i] > self.window:
                try:
                    del self.rts[-i]
                    del self.users[-i]
                except:
                    break
        
        self.time+=[t]
        self.rts+=[self.getResponseTime()]
        self.tr+=[self.getTroughput()]
        self.cores+=[self.getCores()]
        self.replica+=[self.get_replicas(self.serviceName)]
        self.users+=[self.getUsers()]

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
        self.client = docker.from_env()
        self.cores = []
        self.rts = []
        self.tr = []
        self.users = []
        self.time = []
        self.replica = []
        # Aggiunta per il throughput
        self.last_requests = None
        self.last_timestamp = None