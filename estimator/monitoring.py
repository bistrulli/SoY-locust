from pathlib import Path
from config import locustDataDir,serviceName
import pandas as pd
import numpy as np
import docker
from prometheus_api_client import PrometheusConnect
import yaml
import pandas as pd
import requests_unixsocket
import requests
import re

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
        self.time += [t]
        self.rts += [self.getResponseTime()]
        self.tr += [self.getTroughput()]
        self.cores += [self.getCores()]
        self.replica += [self.get_replicas(self.serviceName)]
        self.users += [self.getUsers()]
        self.active_users += [self.get_active_users()]
        # Utilizzo Prometheus per aggregare le metriche CPU e memoria
        totRes = self.getTotalUtilization_via_prometheus()
        self.memory += [totRes["total_mem"]]
        self.util += [totRes["total_cpu"]]

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
        Calcola il tempo di risposta medio degli ultimi 60 secondi utilizzando query Prometheus rate.
        """
        try:
            sum_result = self.prom.custom_query(query="sum(rate(locust_request_latency_seconds_sum[1m]))")
            count_result = self.prom.custom_query(query="sum(rate(locust_request_latency_seconds_count[1m]))")
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
        # Modifica: utilizzare la query per il rate negli ultimi 1 minuto
        try:
            result = self.prom.custom_query(query="sum(rate(locust_requests_total[1m]))")
            if result and len(result) > 0 and 'value' in result[0]:
                throughput = float(result[0]['value'][1])
            else:
                throughput = 0
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

    def getTotalUtilization_via_prometheus(self):
        """
        Recupera l'utilizzo aggregato (CPU e memoria) per il servizio interrogando Prometheus.
        Assicurati che Prometheus stia raccogliendo le metriche dei container (cAdvisor, node exporter, ecc.)
        e che siano applicate etichette come service_name.
        """
        try:
            # Query per il tasso di utilizzo CPU (in secondi) aggregato per il servizio
            query_cpu = f'sum(rate(container_cpu_usage_seconds_total{{service_name="{self.serviceName}"}}[1m]))'
            # Query per l'utilizzo memoria in bytes aggregato per il servizio
            query_mem = f'sum(container_memory_usage_bytes{{service_name="{self.serviceName}"}})'
            
            cpu_result = self.prom.custom_query(query=query_cpu)
            mem_result = self.prom.custom_query(query=query_mem)
            
            total_cpu = float(cpu_result[0]['value'][1]) if cpu_result and 'value' in cpu_result[0] else 0.0
            total_mem = float(mem_result[0]['value'][1]) if mem_result and 'value' in mem_result[0] else 0.0
            return {"total_cpu": total_cpu, "total_mem": total_mem}
        except Exception as e:
            print("Error in getTotalUtilization_via_prometheus:", e)
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
        #numero di utenti attivi cosi come visti da locust
        self.active_users = []

    def save_to_csv(self, filename):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cores": self.cores,
            "rts": self.rts,
            "tr": self.tr,
            "users": self.active_users,
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

    def get_active_users(self):
        """
        Recupera il valore attuale del Gauge 'locust_active_users' tramite una query a Prometheus.
        Assicurati che il job che espone questo metric sia correttamente configurato in Prometheus.
        """
        try:
            query = 'locust_active_users'
            result = self.prom.custom_query(query=query)
            if result and 'value' in result[0]:
                return float(result[0]['value'][1])
            return None
        except Exception as e:
            print("Error fetching active users metric from Prometheus:", e)
            return None

    def get_total_cpu_utilization(self):
        """
        Collects the total CPU utilization for all replicas of the specified service.
        Returns the total CPU utilization in absolute value (CPU seconds per second).
        For example, if you have 2 replicas and each is using 0.5 CPU, the total will be 1.0.
        """
        try:
            # Query for CPU usage rate over 1 minute window
            # This query sums up CPU usage across all replicas of the service
            query = f'sum(rate(container_cpu_usage_seconds_total{{service_name="{self.serviceName}"}}[1m]))'
            result = self.prom.custom_query(query=query)
            
            if result and len(result) > 0 and 'value' in result[0]:
                total_cpu = float(result[0]['value'][1])
                return total_cpu
            return 0.0
        except Exception as e:
            print(f"Error collecting CPU utilization for service {self.serviceName}:", e)
            return 0.0

    def test_cadvisor_configuration(self):
        """
        Tests if cAdvisor is correctly configured and accessible.
        Returns a tuple (bool, str) where:
        - bool: True if cAdvisor is working correctly, False otherwise
        - str: A message explaining the status
        """
        try:
            # Test 1: Check if cAdvisor metrics are available in Prometheus
            query = 'container_cpu_usage_seconds_total'
            result = self.prom.custom_query(query=query)
            
            if not result:
                return False, "No cAdvisor metrics found in Prometheus"
            
            # Test 2: Check if we can see our service metrics
            service_query = f'container_cpu_usage_seconds_total{{service_name="{self.serviceName}"}}'
            service_result = self.prom.custom_query(query=service_query)
            
            if not service_result:
                return False, f"No metrics found for service {self.serviceName}"
            
            # Test 3: Check if we can get a valid CPU reading
            cpu_util = self.get_total_cpu_utilization()
            if cpu_util is None:
                return False, "Could not get valid CPU utilization reading"
            
            return True, "cAdvisor is correctly configured and working"
            
        except Exception as e:
            return False, f"Error testing cAdvisor configuration: {str(e)}"