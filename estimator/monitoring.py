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
                 serviceName="", stack_name="", promHost="localhost", promPort=9090, sysfile=""):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.serviceName = serviceName
        self.stack_name = stack_name
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
        self.memory += [0]
        self.util += [self.get_service_cpu_utilization(self.stack_name,self.serviceName)]

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

    def get_replicas(self, service_name):
        """
        Gets the number of replicas for a service.
        
        Args:
            service_name (str): The name of the service without stack prefix
        """
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

    def get_service_cpu_utilization(self, service_name=None, stack_name=None):
        """
        Gets the total CPU utilization for all replicas of a specific service in a stack using cAdvisor metrics.
        
        Args:
            service_name (str): The name of the service (e.g., 'node')
            stack_name (str, optional): The name of the Docker Swarm stack. If None, uses self.stack_name
        
        Returns:
            float: The total CPU utilization as an absolute value (CPU seconds per second)
        """
        try:
            # Use provided stack_name or fall back to self.stack_name
            stack = stack_name if stack_name is not None else self.stack_name
            # Construct the full service name using f-string
            full_service_name = f"{stack}_{service_name}"
            
            # Query for CPU usage rate over 1 minute window, summed across all replicas
            query = f'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name="{full_service_name}"}}[1m]))'
            result = self.prom.custom_query(query=query)
            
            if result and len(result) > 0 and 'value' in result[0]:
                total_cpu = float(result[0]['value'][1])
                return total_cpu
            return 0.0
        except Exception as e:
            print(f"Error collecting CPU utilization for service {full_service_name}:", e)
            return 0.0