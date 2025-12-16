from pathlib import Path
from config import locustDataDir, serviceName
import pandas as pd
import numpy as np
import docker
from prometheus_api_client import PrometheusConnect
import yaml
import pandas as pd
import requests_unixsocket
import requests
import re
import json
import time
import logging
# Get service info using Docker CLI
import subprocess

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
                 promPort=9090, sysfile="", has_health_check=False, remote_docker_host=None, remote_docker_port=None,
                 disable_prometheus=False):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.serviceName = serviceName
        self.stack_name = stack_name
        self.service_prefix = _get_service_prefix(serviceName, stack_name)
        self.promPort = promPort
        self.promHost = promHost
        self.sysfile = Path(sysfile)
        self.remote_docker_host = remote_docker_host
        self.remote_docker_port = remote_docker_port
        self.has_health_check = has_health_check
        self.disable_prometheus = disable_prometheus

        # Lazy initialization - non creare client nel __init__ per evitare fork issues
        self._client = None
        self._prom = None

        if (not Path(self.sysfile).exists()):
            raise FileNotFoundError(f"File {self.sysfile} not found")

        self.sys = yaml.safe_load(self.sysfile.open())
        self.reset()

    @property
    def client(self):
        """Lazy initialization del Docker client per evitare problemi di fork"""
        if self._client is None:
            if self.remote_docker_host is not None and self.remote_docker_port is not None:
                self._client = docker.DockerClient(
                    base_url='tcp://' + self.remote_docker_host + ":" + str(self.remote_docker_port))
            else:
                self._client = docker.from_env()
        return self._client

    @property
    def prom(self):
        """
        Lazy initialization del Prometheus client per evitare problemi di fork.
        Disabilita connection pooling per evitare thread persistenti.
        """
        if self._prom is None:
            self._prom = PrometheusConnect(url=f"http://{self.promHost}:{self.promPort}", disable_ssl=True)

            # Disabilita connection pooling per evitare thread persistenti
            if hasattr(self._prom, '_session') and self._prom._session:
                # Configura session senza connection pooling
                from requests.adapters import HTTPAdapter

                # Adapter personalizzato con pooling disabilitato
                no_pool_adapter = HTTPAdapter(pool_connections=0, pool_maxsize=0)
                self._prom._session.mount('http://', no_pool_adapter)
                self._prom._session.mount('https://', no_pool_adapter)

                # Patch per gevent compatibility
                self._prom._session.headers.update({'Accept-Encoding': 'identity'})

                logger.debug("%s Prometheus client created with connection pooling disabled", self.service_prefix)

        return self._prom

    def _service_label_regex(self):
        """Costruisce una regex per il label 'service' che copre varianti con stack e @docker (legacy)."""
        names = [
            self.serviceName,
            f"{self.stack_name}_{self.serviceName}",
            f"{self.serviceName}@docker",
            f"{self.stack_name}_{self.serviceName}@docker",
        ]
        # dedup
        seen = set()
        uniq = []
        for n in names:
            if n and n not in seen:
                uniq.append(n)
                seen.add(n)
        return "(" + "|".join(uniq) + ")"

    def get_nginx_vts_metrics_summary(self):
        """
        Restituisce un summary di tutte le metriche VTS disponibili per il servizio.
        Utile per debugging e validazione dell'implementazione nginx-vts.

        Returns:
            dict: Dictionary con le metriche VTS principali
        """
        try:
            summary = {
                'service_name': self.serviceName,
                'stack_name': self.stack_name,
                'throughput_2xx': 0,
                'throughput_total': 0,
                'response_time_seconds': 0,
                'cpu_utilization': 0,
                'active_replicas': 0,
                'configured_replicas': 0
            }

            # Throughput 2xx
            query_2xx = f'rate(nginx_vts_server_requests_total{{service="{self.serviceName}",code="2xx",host="localhost"}}[30s])'
            result_2xx = self.prom.custom_query(query=query_2xx)
            if result_2xx and len(result_2xx) > 0 and 'value' in result_2xx[0]:
                summary['throughput_2xx'] = float(result_2xx[0]['value'][1])

            # Throughput total
            query_total = f'rate(nginx_vts_server_requests_total{{service="{self.serviceName}",code="total",host="localhost"}}[30s])'
            result_total = self.prom.custom_query(query=query_total)
            if result_total and len(result_total) > 0 and 'value' in result_total[0]:
                summary['throughput_total'] = float(result_total[0]['value'][1])

            # Response time (usa i metodi esistenti)
            summary['response_time_seconds'] = self.getResponseTime()
            summary['cpu_utilization'] = self.get_service_cpu_utilization()
            summary['active_replicas'] = self.get_replicas(self.stack_name, self.serviceName)

            logger.info("%s VTS Metrics Summary: %s", self.service_prefix, summary)
            return summary

        except Exception as e:
            logger.error("%s Error generating VTS metrics summary: %s", self.service_prefix, e)
            return {}

    def tick(self, t):
        self.time += [t]
        self.rts += [self.getResponseTime()]
        self.tr += [self.getTroughput()]
        self.arrival_rate += [self.getArrivalRate()]  # Nuovo: arrival rate per queuing model
        self.cores += [self.getCores()]
        self.replica += [self.get_replicas(self.stack_name, self.serviceName)]
        self.ready_replica += [self.get_ready_replicas(self.stack_name, self.serviceName)]
        self.users += [self.getUsers()]
        self.active_users += [self.get_active_users()]
        self.memory += [0]
        self.util += [self.get_service_cpu_utilization(stack_name=self.stack_name, service_name=self.serviceName)]

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
        Calcola il tempo di risposta medio del servizio utilizzando nginx-vts metrics.
        Ritorna il response time in secondi basato su rate degli ultimi 30s.
        """
        if self.disable_prometheus:
            logger.debug("%s Prometheus disabled - returning mock response time", self.service_prefix)
            return 0.1  # Mock response time

        try:
            # Query per numeratore: tempo totale speso nelle richieste
            time_query = f'rate(nginx_vts_server_request_seconds_total{{service="{self.serviceName}",host="localhost"}}[30s])'
            time_result = self.prom.custom_query(query=time_query)

            # Query per denominatore: numero totale di richieste
            req_query = f'rate(nginx_vts_server_requests_total{{service="{self.serviceName}",host="localhost",code="total"}}[30s])'
            req_result = self.prom.custom_query(query=req_query)

            # Estrae i valori
            if (time_result and len(time_result) > 0 and 'value' in time_result[0] and
                    req_result and len(req_result) > 0 and 'value' in req_result[0]):

                total_time = float(time_result[0]['value'][1])
                total_requests = float(req_result[0]['value'][1])

                # Calcola response time medio (evita divisione per zero)
                if total_requests > 0:
                    response_time = total_time / total_requests
                    logger.debug("%s VTS Response time calculated: %s seconds", self.service_prefix, response_time)
                    return response_time
                else:
                    logger.debug("%s VTS No requests found, returning 0", self.service_prefix)
                    return 0
            else:
                logger.warning("%s VTS No valid response time data found for service %s",
                               self.service_prefix, self.serviceName)
                return 0

        except Exception as e:
            logger.error("%s VTS Error calculating response time for service %s: %s",
                         self.service_prefix, self.serviceName, e)
            return 0

    def getArrivalRate(self):
        """
        Calcola l'arrival rate del servizio specifico utilizzando le metriche nginx-vts.
        Ritorna il numero totale di richieste in arrivo per secondo negli ultimi 30s.
        """
        if self.disable_prometheus:
            logger.debug("%s Prometheus disabled - returning mock arrival rate", self.service_prefix)
            return 6.0  # Mock arrival rate

        try:
            # Usa nginx-vts per tutte le richieste in arrivo (totali) per il servizio specifico
            query = f'rate(nginx_vts_server_requests_total{{service="{self.serviceName}",code="total",host="localhost"}}[30s])'
            result = self.prom.custom_query(query=query)

            if result and len(result) > 0 and 'value' in result[0]:
                arrival_rate = float(result[0]['value'][1])
                logger.debug("%s VTS Arrival rate calculated: %s req/s", self.service_prefix, arrival_rate)
                return arrival_rate

            logger.warning("%s VTS No arrival rate data found for service %s",
                           self.service_prefix, self.serviceName)
            return 0

        except Exception as e:
            logger.error("%s VTS Error querying arrival rate for service %s: %s",
                         self.service_prefix, self.serviceName, e)
            return 0

    def getTroughput(self):
        """
        Calcola il throughput del servizio specifico utilizzando le metriche nginx-vts.
        Ritorna il numero di richieste di successo (2xx) per secondo negli ultimi 30s.
        """
        if self.disable_prometheus:
            logger.debug("%s Prometheus disabled - returning mock throughput", self.service_prefix)
            return 5.0  # Mock throughput

        try:
            # Usa nginx-vts per richieste di successo (2xx) per il servizio specifico
            query = f'rate(nginx_vts_server_requests_total{{service="{self.serviceName}",code="2xx",host="localhost"}}[30s])'
            result = self.prom.custom_query(query=query)

            if result and len(result) > 0 and 'value' in result[0]:
                throughput = float(result[0]['value'][1])
                logger.debug("%s VTS Throughput calculated: %s req/s", self.service_prefix, throughput)
                return throughput

            # Se non ci sono richieste 2xx, prova con tutte le richieste
            fallback_query = f'rate(nginx_vts_server_requests_total{{service="{self.serviceName}",code="total",host="localhost"}}[30s])'
            fallback_result = self.prom.custom_query(query=fallback_query)

            if fallback_result and len(fallback_result) > 0 and 'value' in fallback_result[0]:
                throughput = float(fallback_result[0]['value'][1])
                logger.debug("%s VTS Fallback throughput calculated: %s req/s", self.service_prefix, throughput)
                return throughput

            logger.warning("%s VTS No throughput data found for service %s",
                           self.service_prefix, self.serviceName)
            return 0

        except Exception as e:
            logger.error("%s VTS Error querying throughput for service %s: %s",
                         self.service_prefix, self.serviceName, e)
            return 0

    def get_replicas(self, stack_name, service_name):
        """
        Gets the number of replicas for a service using both Docker API and Prometheus metrics.
        Falls back to counting active containers if Docker API fails.

        Args:
            stack_name (str): The name of the stack
            service_name (str): The name of the service without stack prefix

        Returns:
            int: Number of configured replicas for the service
        """
        try:
            # Primary method: Use Docker API
            full_service_name = f"{stack_name}_{service_name}"
            logger.debug("Attempting to get replicas for service: '%s'", full_service_name)

            service = self.client.services.get(full_service_name)
            replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
            logger.debug("Docker API replica count: %s", replicas)
            return replicas

        except docker.errors.NotFound:
            logger.warning("%s Service '%s' not found via Docker API, trying Prometheus count",
                           self.service_prefix, full_service_name)
        except Exception as e:
            logger.warning("%s Docker API error for service %s: %s, trying Prometheus count",
                           self.service_prefix, full_service_name, e)

        # Fallback method: Count active containers via Prometheus
        try:
            query = f'count(container_cpu_usage_seconds_total{{container_label_com_docker_compose_service="{service_name}"}})'
            logger.debug("Prometheus replica count query: %s", query)

            result = self.prom.custom_query(query=query)
            if result and len(result) > 0 and 'value' in result[0]:
                count = int(float(result[0]['value'][1]))
                logger.debug("Prometheus container count: %s", count)
                return count
            else:
                logger.warning("%s No containers found for service %s", self.service_prefix, service_name)
                return 0

        except Exception as e:
            logger.error("%s Error counting replicas via Prometheus for service %s: %s",
                         self.service_prefix, service_name, e)
            return 0

    def get_ready_replicas(self, stack_name, service_name):
        """
        Gets the number of replicas for a service that are actually ready to process requests.
        This means containers that are in running state and have passed health checks (if configured).

        Args:
            stack_name (str): The name of the stack
            service_name (str): The name of the service without stack prefix

        Returns:
            int: Number of ready replicas
        """
        try:
            # Construct the full service name
            full_service_name = f"{stack_name}_{service_name}"

            # Get all tasks for this service with their status
            # cmd = ["docker", "service", "ps", "--format", "{{.CurrentState}}", full_service_name]
            cmd = []
            env = {}
            if self.remote_docker_host is not None:
                env["DOCKER_HOST"] = "tcp://" + self.remote_docker_host + ":" + str(self.remote_docker_port)
            cmd.append("docker")
            cmd.append("service")
            cmd.append("ps")
            cmd.append("--format")
            cmd.append("{{.CurrentState}}")
            cmd.append(full_service_name)
            print(cmd)

            output = subprocess.check_output(cmd, env=env, universal_newlines=True)

            # Count only "Running" tasks
            task_states = output.strip().split('\n')
            # Filter lines that start with "Running" and are not empty
            ready_count = sum(1 for state in task_states if state and state.startswith("Running"))

            logger.debug("Service %s: found %d running replicas", full_service_name, ready_count)

            # If the service has health checks, we need to count only healthy containers
            if self.has_health_check:
                try:
                    # Get task IDs for the service tasks
                    # cmd = ["docker", "service", "ps", "--format", "{{.ID}}", full_service_name]
                    cmd = []
                    env = {}
                    if self.remote_docker_host is not None:
                        env["DOCKER_HOST"] = "tcp://" + self.remote_docker_host + ":" + str(self.remote_docker_port)
                    cmd.append("docker")
                    cmd.append("service")
                    cmd.append("ps")
                    cmd.append("--format")
                    cmd.append("{{.ID}}")
                    cmd.append(full_service_name)
                    print(cmd)

                    task_ids = subprocess.check_output(cmd, env=env, universal_newlines=True).strip().split('\n')

                    # Get container IDs from task IDs
                    container_ids = []
                    for task_id in task_ids:
                        if not task_id:
                            continue
                        # Get container ID for the task
                        #                        cmd = ["docker", "inspect", "--format", "{{.Status.ContainerStatus.ContainerID}}", task_id]
                        cmd = []
                        env = {}
                        if self.remote_docker_host is not None:
                            env["DOCKER_HOST"] = "tcp://" + self.remote_docker_host + ":" + str(self.remote_docker_port)
                        cmd.append("docker")
                        cmd.append("inspect")
                        cmd.append("--format")
                        cmd.append("{{.Status.ContainerStatus.ContainerID}}")
                        cmd.append(task_id)

                        try:
                            container_id = subprocess.check_output(cmd, env=env, universal_newlines=True).strip()
                            if container_id:
                                container_ids.append(container_id)
                        except:
                            pass

                    healthy_count = 0
                    for container_id in container_ids:
                        # Get container health status
                        #                        cmd = ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", container_id]
                        cmd = []
                        env = {}
                        if self.remote_docker_host is not None:
                            env["DOCKER_HOST"] = "tcp://" + self.remote_docker_host + ":" + str(self.remote_docker_port)
                        cmd.append("docker")
                        cmd.append("inspect")
                        cmd.append("--format")
                        cmd.append("{{ifw .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}")
                        cmd.append(container_id)

                        try:
                            health_status = subprocess.check_output(cmd, universal_newlines=True).strip()
                            logger.debug("Container %s: Health status = %s", container_id[:12], health_status)
                            if health_status == "healthy":
                                healthy_count += 1
                        except Exception as e:
                            logger.debug("Error checking health for container %s: %s", container_id[:12], str(e))

                    logger.debug("Service %s: found %d healthy containers out of %d containers", full_service_name,
                                 healthy_count, len(container_ids))
                    return healthy_count
                except Exception as e:
                    logger.debug("Error checking container health: %s", str(e))
                    # Fall back to running count
                    return ready_count
            else:
                # If no health checks, return the number of running containers
                return ready_count

        except Exception as e:
            logger.error("%s Error in get_ready_replicas: %s", self.service_prefix, str(e))
            # Fallback to nominal replica count
            return self.get_replicas(stack_name, service_name)

    def reset(self):
        self.cores = []
        self.rts = []
        self.tr = []
        self.arrival_rate = []  # Nuovo: storico arrival rate
        self.users = []
        self.time = []
        self.replica = []
        self.ready_replica = []
        self.util = []
        self.memory = []
        self.last_requests = None
        self.last_timestamp = None
        self.active_users = []

    def save_to_csv(self, filename):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Verifico la lunghezza di tutti gli array
        lengths = {
            "cores": len(self.cores),
            "rts": len(self.rts),
            "tr": len(self.tr),
            "arrival_rate": len(self.arrival_rate),
            "users": len(self.active_users),
            "replica": len(self.replica),
            "ready_replica": len(self.ready_replica),
            "util": len(self.util),
            "mem": len(self.memory),
        }

        logger.info("%s Saving results", self.service_prefix)
        logger.info("%s Array lengths: %s", self.service_prefix, lengths)

        # Trovo la lunghezza minima comune
        min_length = min(lengths.values()) if lengths else 0

        # Creo un dizionario di dati
        data = {
            "cores": self.cores[:min_length],
            "rts": self.rts[:min_length],
            "tr": self.tr[:min_length],
            "arrival_rate": self.arrival_rate[:min_length],
            "users": self.active_users[:min_length],
            "replica": self.replica[:min_length],
            "ready_replica": self.ready_replica[:min_length],
            "util": self.util[:min_length],
            "mem": self.memory[:min_length],
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
        if self.disable_prometheus:
            logger.debug("%s Prometheus disabled - returning mock active users", self.service_prefix)
            return 2.0  # Mock active users

        try:
            query = 'locust_active_users'
            result = self.prom.custom_query(query=query)
            if result and 'value' in result[0]:
                return float(result[0]['value'][1])
            return 0.0
        except Exception as e:
            logger.error("%s Error fetching active users metric from Prometheus: %s", self.service_prefix, e)
            return 0.0

    def get_service_cpu_utilization(self, service_name=None, stack_name=None):
        """
        Gets the total CPU utilization for all replicas of a specific service using cAdvisor metrics.
        Uses container_label_com_docker_compose_service for better compatibility.

        Args:
            service_name (str): The name of the service (e.g., 'node')
            stack_name (str, optional): The name of the Docker Swarm stack. If None, uses self.stack_name

        Returns:
            float: The total CPU utilization as an absolute value (CPU seconds per second)
        """
        if self.disable_prometheus:
            logger.debug("%s Prometheus disabled - returning mock CPU utilization", self.service_prefix)
            return 0.5  # Mock CPU utilization

        try:
            service = service_name if service_name is not None else self.serviceName
            logger.debug("CPU Input parameters - service_name: '%s'", service)

            # Query using compose service label (more reliable than swarm service name)
            query = f'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_compose_service="{service}"}}[30s]))'
            logger.debug("CPU Prometheus query: %s", query)

            result = self.prom.custom_query(query=query)
            logger.debug("CPU Raw Prometheus result: %s", result)

            if result and len(result) > 0 and 'value' in result[0]:
                total_cpu = float(result[0]['value'][1])
                logger.debug("%s CPU utilization calculated: %s CPU seconds/second", self.service_prefix, total_cpu)
                return total_cpu
            else:
                logger.debug("%s CPU No CPU data found for service %s", self.service_prefix, service)
                return 0.0

        except Exception as e:
            logger.error("%s CPU Error collecting CPU utilization for service %s: %s",
                         self.service_prefix, service, e)
            return 0.0

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

    def predict_arrival_rate(self, horizon=1):
        """
        Predice l'arrival rate futuro basandosi sul gradiente medio degli ultimi 5 step.
        Modella ogni servizio come un queuing center aperto con arrival rate variabile.

        Args:
            horizon (int): Numero di step nel futuro per la predizione (default: 1)

        Returns:
            float: Arrival rate predetto dopo 'horizon' step (richieste/secondo)
        """
        # Filtra i valori None/zero dalla lista degli arrival rate
        valid_data = [(t, ar) for t, ar in zip(self.time, self.arrival_rate) if ar is not None and ar > 0]

        if len(valid_data) < 5:
            # Se non abbiamo abbastanza dati validi, ritorna l'ultimo valore valido o 0
            return valid_data[-1][1] if valid_data else 0
        else:
            logger.debug("%s Arrival rate valid data: %s", self.service_prefix, valid_data[-5:])

        # Prendi gli ultimi 5 valori validi
        recent_data = valid_data[-5:]
        recent_times = [t for t, _ in recent_data]
        recent_arrival_rates = [ar for _, ar in recent_data]

        # Calcola i gradienti per ogni coppia di punti consecutivi
        gradients = []
        for i in range(1, len(recent_arrival_rates)):
            dt = recent_times[i] - recent_times[i - 1]
            if dt > 0:  # Evita divisione per zero
                gradient = (recent_arrival_rates[i] - recent_arrival_rates[i - 1]) / dt
                gradients.append(gradient)

        if not gradients:
            return recent_arrival_rates[-1]  # Ritorna l'ultimo valore se non possiamo calcolare gradienti

        # Calcola il gradiente medio
        avg_gradient = sum(gradients) / len(gradients)

        # Stima il tempo per l'orizzonte di predizione (assumendo step costanti)
        avg_dt = (recent_times[-1] - recent_times[-2])
        prediction_dt = avg_dt * horizon

        # Predici l'arrival rate (non può essere negativo)
        predicted_arrival_rate = max(0, recent_arrival_rates[-1] + avg_gradient * prediction_dt)

        logger.debug("%s Predicted arrival rate: %.4f req/s (horizon=%d, gradient=%.4f)",
                     self.service_prefix, predicted_arrival_rate, horizon, avg_gradient)

        return predicted_arrival_rate

    def __str__(self):
        return f"Monitoring(window={self.window}, sla={self.sla})"
