from pathlib import Path
from config import locustDataDir, serviceName
import pandas as pd
import numpy as np
from prometheus_api_client import PrometheusConnect
import yaml
import logging

# Configure logging for this module
logger = logging.getLogger(__name__)

def _get_service_prefix(service_name, stack_name):
    """Helper per creare un prefisso leggibile per i log"""
    if service_name:
        return f"[{service_name.upper()}]"
    elif stack_name:
        return f"[{stack_name}]"
    else:
        return "[MONITOR]"


class Monitoring:
    def __init__(self, window, sla, reducer=lambda x: sum(x) / len(x),
                 serviceName="", stack_name="", promHost="localhost",
                 promPort=9090, sysfile="", has_health_check=False, remote=None, remote_docker_port=None):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.serviceName = serviceName
        self.stack_name = stack_name
        self.service_prefix = _get_service_prefix(serviceName, stack_name)
        self.promPort = promPort
        self.promHost = promHost
        self.sysfile = sysfile
        self.has_health_check = has_health_check
        
        # Lazy initialization
        self._prom = None
        
        if (not Path(self.sysfile).exists()):
            raise FileNotFoundError(f"File {self.sysfile} not found")
        self.sys = yaml.safe_load(self.sysfile.open())
        self.reset()


    @property  
    def prom(self):
        """Lazy initialization del Prometheus client per evitare problemi di fork"""
        if self._prom is None:
            self._prom = PrometheusConnect(url=f"http://{self.promHost}:{self.promPort}", disable_ssl=True)
            # Patch per gevent compatibility
            if hasattr(self._prom, '_session') and self._prom._session:
                self._prom._session.headers.update({'Accept-Encoding': 'identity'})
        return self._prom

    def _get_cluster_name(self, service_name):
        """Deriva il nome del cluster Envoy dal nome del servizio"""
        return f"{service_name.replace('-', '_')}_cluster"

    def _get_service_label_regex(self, stack_name, service_name):
        """Costruisce una regex per cAdvisor service labels"""
        return f"{stack_name}_{service_name}.*"

    def tick(self, t):
        self.time += [t]
        self.rts += [self.getResponseTime()]
        self.tr += [self.getTroughput()]
        self.cores += [self.getCores()]
        self.replica += [self.get_replicas(self.stack_name, self.serviceName)]
        self.ready_replica += [self.get_ready_replicas(self.stack_name, self.serviceName)]
        self.users += [self.getUsers()]
        self.active_users += [self.get_active_users()]
        self.memory += [0]
        self.util += [self.get_service_cpu_utilization(stack_name=self.stack_name, service_name=self.serviceName)]
        
        # Add Envoy metrics
        self.envoy_incoming_rps += [self.get_incoming_rps()]
        self.envoy_completed_rps += [self.get_completed_rps()]

    def getUsers(self):
        # torno il numero di utenti attivi (Little's Law)
        return self.rts[-1] * self.tr[-1]

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
    def query_prometheus(self, metric_name):
        result = self.prom.custom_query(query=metric_name)
        return result

    def getResponseTime(self):
        """
        Calcola il tempo di risposta medio del servizio specifico utilizzando Envoy.
        """
        return self.get_response_time()

    def getTroughput(self):
        """
        Calcola il throughput del servizio specifico utilizzando Envoy.
        """
        return self.get_completed_rps()

    def get_replicas(self, stack_name, service_name):
        """
        Gets the number of replicas for a service using cAdvisor metrics.
        Returns the same value as get_active_replicas.

        Args:
            stack_name (str): The name of the Docker Swarm stack
            service_name (str): The name of the service without stack prefix
        """
        return self.get_active_replicas(stack_name, service_name)

    def get_ready_replicas(self, stack_name, service_name):
        """
        Gets the number of ready replicas using cAdvisor metrics.
        Returns the same value as get_active_replicas.

        Args:
            stack_name (str): The name of the Docker Swarm stack
            service_name (str): The name of the service without stack prefix

        Returns:
            int: Number of ready replicas
        """
        return self.get_active_replicas(stack_name, service_name)

    def reset(self):
        self.cores = []
        self.rts = []
        self.tr = []
        self.users = []
        self.time = []
        self.replica = []
        self.ready_replica = []
        self.util = []
        self.memory = []
        self.last_requests = None
        self.last_timestamp = None
        self.active_users = []
        
        # Add Envoy metrics lists
        self.envoy_incoming_rps = []
        self.envoy_completed_rps = []

    def save_to_csv(self, filename):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Verifico la lunghezza di tutti gli array
        lengths = {
            "cores": len(self.cores),
            "rts": len(self.rts),
            "tr": len(self.tr),
            "users": len(self.active_users),
            "replica": len(self.replica),
            "ready_replica": len(self.ready_replica),
            "util": len(self.util),
            "mem": len(self.memory),
            "envoy_incoming_rps": len(self.envoy_incoming_rps),
            "envoy_completed_rps": len(self.envoy_completed_rps)
        }

        logger.info("%s Saving results", self.service_prefix)
        logger.info("%s Array lengths: %s", self.service_prefix, lengths)

        # Trovo la lunghezza minima comune
        min_length = min(lengths.values())

        # Creo un dizionario di dati
        data = {
            "cores": self.cores[:min_length],
            "rts": self.rts[:min_length],
            "tr": self.tr[:min_length],
            "users": self.active_users[:min_length],
            "replica": self.replica[:min_length],
            "ready_replica": self.ready_replica[:min_length],
            "util": self.util[:min_length],
            "mem": self.memory[:min_length],
            "envoy_incoming_rps": self.envoy_incoming_rps[:min_length],
            "envoy_completed_rps": self.envoy_completed_rps[:min_length]
        }

        try:
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
            logger.info("%s Data saved to %s (truncated to %d rows)", self.service_prefix, filename, min_length)
        except Exception as e:
            logger.error("%s Error saving data: %s", self.service_prefix, e)

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
            logger.error("%s Error fetching active users metric from Prometheus: %s", self.service_prefix, e)
            return None

    def get_service_cpu_utilization(self, service_name=None, stack_name=None):
        """
        Gets the total CPU utilization for all replicas of a specific service using cAdvisor metrics.
        Query: sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_swarm_service_name=~"<STACK>_<SERVICE>.*"}[1m]))

        Args:
            service_name (str): The name of the service (e.g., 'node')
            stack_name (str, optional): The name of the Docker Swarm stack. If None, uses self.stack_name

        Returns:
            float: The total CPU utilization as an absolute value (CPU seconds per second)
        
        Raises:
            RuntimeError: If the query returns no data or invalid data
        """
        # Use provided parameters or fall back to instance variables
        stack = stack_name if stack_name is not None else self.stack_name
        service = service_name if service_name is not None else self.serviceName
        
        if not stack or not service:
            raise RuntimeError(f"get_service_cpu_utilization: Missing stack_name ('{stack}') or service_name ('{service}'). Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
        
        # Construct the query using the exact format from README-ENVOY.md
        service_label_regex = self._get_service_label_regex(stack, service)
        query = f'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name=~"{service_label_regex}"}}[1m]))'
        
        try:
            result = self.prom.custom_query(query=query)
            
            if not result or len(result) == 0:
                raise RuntimeError(f"get_service_cpu_utilization: No metrics found for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            if 'value' not in result[0]:
                raise RuntimeError(f"get_service_cpu_utilization: Invalid result format for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            total_cpu = float(result[0]['value'][1])
            return total_cpu
            
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"get_service_cpu_utilization: Error for service_name='{service}', stack_name='{stack}'. Query: {query}. Error: {e}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")

    def get_incoming_rps(self, service_name=None, stack_name=None):
        """
        Gets incoming request rate using Envoy metrics.
        Query: rate(envoy_cluster_upstream_rq_total{envoy_cluster_name="<CLUSTER_NAME>"}[1m])

        Args:
            service_name (str, optional): Service name. If None, uses self.serviceName
            stack_name (str, optional): Stack name. If None, uses self.stack_name

        Returns:
            float: Incoming requests per second

        Raises:
            RuntimeError: If the query returns no data or invalid data
        """
        # Use provided parameters or fall back to instance variables
        service = service_name if service_name is not None else self.serviceName
        stack = stack_name if stack_name is not None else self.stack_name
        
        if not service:
            raise RuntimeError(f"get_incoming_rps: Missing service_name ('{service}'). Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
        
        cluster_name = self._get_cluster_name(service)
        query = f'rate(envoy_cluster_upstream_rq_total{{envoy_cluster_name="{cluster_name}"}}[1m])'
        
        try:
            result = self.prom.custom_query(query=query)
            
            if not result or len(result) == 0:
                raise RuntimeError(f"get_incoming_rps: No metrics found for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            if 'value' not in result[0]:
                raise RuntimeError(f"get_incoming_rps: Invalid result format for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            return float(result[0]['value'][1])
            
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"get_incoming_rps: Error for service_name='{service}', stack_name='{stack}'. Query: {query}. Error: {e}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")

    def get_completed_rps(self, service_name=None, stack_name=None):
        """
        Gets completed request rate using Envoy metrics.
        Query: rate(envoy_cluster_upstream_rq_completed{envoy_cluster_name="<CLUSTER_NAME>"}[1m])

        Args:
            service_name (str, optional): Service name. If None, uses self.serviceName
            stack_name (str, optional): Stack name. If None, uses self.stack_name

        Returns:
            float: Completed requests per second

        Raises:
            RuntimeError: If the query returns no data or invalid data
        """
        # Use provided parameters or fall back to instance variables
        service = service_name if service_name is not None else self.serviceName
        stack = stack_name if stack_name is not None else self.stack_name
        
        if not service:
            raise RuntimeError(f"get_completed_rps: Missing service_name ('{service}'). Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
        
        cluster_name = self._get_cluster_name(service)
        query = f'rate(envoy_cluster_upstream_rq_completed{{envoy_cluster_name="{cluster_name}"}}[1m])'
        
        try:
            result = self.prom.custom_query(query=query)
            
            if not result or len(result) == 0:
                raise RuntimeError(f"get_completed_rps: No metrics found for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            if 'value' not in result[0]:
                raise RuntimeError(f"get_completed_rps: Invalid result format for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            return float(result[0]['value'][1])
            
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"get_completed_rps: Error for service_name='{service}', stack_name='{stack}'. Query: {query}. Error: {e}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")

    def get_response_time(self, service_name=None, stack_name=None):
        """
        Gets average response time using Envoy metrics.
        Query: rate(envoy_cluster_upstream_rq_time_sum{envoy_cluster_name="<CLUSTER_NAME>"}[1m]) / rate(envoy_cluster_upstream_rq_time_count{envoy_cluster_name="<CLUSTER_NAME>"}[1m])

        Args:
            service_name (str, optional): Service name. If None, uses self.serviceName
            stack_name (str, optional): Stack name. If None, uses self.stack_name

        Returns:
            float: Average response time in seconds

        Raises:
            RuntimeError: If the query returns no data or invalid data
        """
        # Use provided parameters or fall back to instance variables
        service = service_name if service_name is not None else self.serviceName
        stack = stack_name if stack_name is not None else self.stack_name
        
        if not service:
            raise RuntimeError(f"get_response_time: Missing service_name ('{service}'). Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
        
        cluster_name = self._get_cluster_name(service)
        query = f'rate(envoy_cluster_upstream_rq_time_sum{{envoy_cluster_name="{cluster_name}"}}[1m]) / rate(envoy_cluster_upstream_rq_time_count{{envoy_cluster_name="{cluster_name}"}}[1m])'
        
        try:
            result = self.prom.custom_query(query=query)
            
            if not result or len(result) == 0:
                raise RuntimeError(f"get_response_time: No metrics found for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            if 'value' not in result[0]:
                raise RuntimeError(f"get_response_time: Invalid result format for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            response_time = float(result[0]['value'][1])
            
            # Check for division by zero or invalid response time
            if response_time <= 0:
                raise RuntimeError(f"get_response_time: Invalid response time value ({response_time}) for service_name='{service}', stack_name='{stack}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            return response_time
            
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"get_response_time: Error for service_name='{service}', stack_name='{stack}'. Query: {query}. Error: {e}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")

    def get_active_replicas(self, stack_name, service_name):
        """
        Gets the number of active replicas using cAdvisor metrics.
        Query: count(container_last_seen{container_label_com_docker_swarm_service_name=~"<STACK>_<SERVICE>.*"})

        Args:
            stack_name (str): The name of the Docker Swarm stack
            service_name (str): The name of the service without stack prefix

        Returns:
            int: Number of active replicas

        Raises:
            RuntimeError: If the query returns no data or invalid data
        """
        if not stack_name or not service_name:
            raise RuntimeError(f"get_active_replicas: Missing stack_name ('{stack_name}') or service_name ('{service_name}'). Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
        
        service_label_regex = self._get_service_label_regex(stack_name, service_name)
        query = f'count(container_last_seen{{container_label_com_docker_swarm_service_name=~"{service_label_regex}"}})'
        
        try:
            result = self.prom.custom_query(query=query)
            
            if not result or len(result) == 0:
                raise RuntimeError(f"get_active_replicas: No metrics found for service_name='{service_name}', stack_name='{stack_name}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            if 'value' not in result[0]:
                raise RuntimeError(f"get_active_replicas: Invalid result format for service_name='{service_name}', stack_name='{stack_name}'. Query: {query}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")
            
            replica_count = int(float(result[0]['value'][1]))
            return replica_count
            
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"get_active_replicas: Error for service_name='{service_name}', stack_name='{stack_name}'. Query: {query}. Error: {e}. Check prometheus/prometheus-envoy.yml and README-ENVOY.md")

    def predict_users(self, horizon=1):
        """
        Predice il numero di utenti futuri basandosi sul gradiente medio degli ultimi 5 step.
        Gestisce i valori None nella lista degli utenti attivi.

        Args:
            horizon (int): Numero di step nel futuro per la predizione (default: 1)

        Returns:
            float: Numero predetto di utenti dopo 'horizon' step
        """
        # Filtra i valori None dalla lista degli utenti attivi
        valid_data = [(t, u) for t, u in zip(self.time, self.active_users) if u is not None]

        if len(valid_data) < 5:
            # Se non abbiamo abbastanza dati validi, ritorna l'ultimo valore valido o 0
            return valid_data[-1][1] if valid_data else 0
        else:
            logger.debug("Valid data: %s", valid_data)

        # Prendi gli ultimi 5 valori validi
        recent_data = valid_data[-5:]
        recent_times = [t for t, _ in recent_data]
        recent_users = [u for _, u in recent_data]

        # Calcola i gradienti per ogni coppia di punti consecutivi
        gradients = []
        for i in range(1, len(recent_users)):
            dt = recent_times[i] - recent_times[i - 1]
            if dt > 0:  # Evita divisione per zero
                gradient = (recent_users[i] - recent_users[i - 1]) / dt
                gradients.append(gradient)

        if not gradients:
            return recent_users[-1]  # Ritorna l'ultimo valore se non possiamo calcolare gradienti

        # Calcola il gradiente medio
        avg_gradient = sum(gradients) / len(gradients)

        # Stima il tempo per l'orizzonte di predizione (assumendo step costanti)
        avg_dt = (recent_times[-1] - recent_times[-2])

        prediction_dt = avg_dt * horizon

        # Predici il numero di utenti
        predicted_users = max(0, recent_users[-1] + avg_gradient * prediction_dt)

        return predicted_users

    def __str__(self):
        return f"Monitoring(window={self.window}, sla={self.sla})"
