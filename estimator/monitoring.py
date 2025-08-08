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
        if remote is not None and remote_docker_port is not None:
            self.client = docker.DockerClient(base_url='tcp://'+remote+":"+str(remote_docker_port))
        else:
            self.client = docker.from_env()
        self.has_health_check = has_health_check
        if (not Path(self.sysfile).exists()):
            raise FileNotFoundError(f"File {self.sysfile} not found")
        self.sys = yaml.safe_load(self.sysfile.open())
        self.prom = PrometheusConnect(url=f"http://{self.promHost}:{self.promPort}", disable_ssl=True)
        self.remote = remote
        self.reset()

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
        
        # Aggiungi le nuove metriche Traefik
        self.traefik_incoming += [self.getIncomingRequestsFromTraefik()]
        self.traefik_completed += [self.getCompletedRequestsFromTraefik()]
        self.traefik_failed += [self.getFailedRequestsFromTraefik()]
        self.traefik_response_time += [self.getResponseTimeFromTraefik()]

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
            logger.error("%s Error querying Prometheus for RT: %s", self.service_prefix, e)
            return 0

    def getTroughput(self):
        # Modifica: utilizzare la query per il rate negli ultimi 1 minuto
        try:
            result = self.prom.custom_query(query="sum(rate(locust_requests_total[30s]))")
            if result and len(result) > 0 and 'value' in result[0]:
                throughput = float(result[0]['value'][1])
            else:
                throughput = 0
            return throughput
        except Exception as e:
            logger.error("%s Error querying throughput from Prometheus: %s", self.service_prefix, e)
            return 0

    def get_replicas(self, stack_name, service_name):
        """
        Gets the number of replicas for a service.

        Args:
            service_name (str): The name of the service without stack prefix
        """
        try:
            # Construct the full service name using stack_name and service_name
            full_service_name = f"{stack_name}_{service_name}"
            logger.debug("Attempting to get replicas for service: '%s'", full_service_name)
            logger.debug("Available services: %s", [service.name for service in self.client.services.list()])

            service = self.client.services.get(full_service_name)
            logger.debug("Found service: %s", service.name)
            logger.debug("Service attributes: %s", service.attrs)

            replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
            logger.debug("Number of replicas: %s", replicas)
            return replicas
        except docker.errors.NotFound:
            logger.error("%s Service '%s' not found", self.service_prefix, full_service_name)
            return None
        except Exception as e:
            logger.error("%s Error in get_replicas: %s", self.service_prefix, str(e))
            logger.error("Error type: %s", type(e))
            return None

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
            if self.remote is not None:
                cmd.append("ssh")
                cmd.append(self.remote)
            cmd.append("docker")
            cmd.append("service")
            cmd.append("ps")
            cmd.append("--format")
            cmd.append("{{.CurrentState}}")
            cmd.append(full_service_name)

            output = subprocess.check_output(cmd, universal_newlines=True)

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
                    if self.remote is not None:
                        cmd.append("ssh")
                        cmd.append(self.remote)
                    cmd.append("docker")
                    cmd.append("service")
                    cmd.append("ps")
                    cmd.append("--format")
                    cmd.append("{{.ID}}")
                    cmd.append(full_service_name)

                    task_ids = subprocess.check_output(cmd, universal_newlines=True).strip().split('\n')

                    # Get container IDs from task IDs
                    container_ids = []
                    for task_id in task_ids:
                        if not task_id:
                            continue
                        # Get container ID for the task
                        #                        cmd = ["docker", "inspect", "--format", "{{.Status.ContainerStatus.ContainerID}}", task_id]
                        cmd = []
                        if self.remote is not None:
                            cmd.append("ssh")
                            cmd.append(self.remote)
                        cmd.append("docker")
                        cmd.append("inspect")
                        cmd.append("--format")
                        cmd.append("{{.Status.ContainerStatus.ContainerID}}")
                        cmd.append(task_id)

                        try:
                            container_id = subprocess.check_output(cmd, universal_newlines=True).strip()
                            if container_id:
                                container_ids.append(container_id)
                        except:
                            pass

                    healthy_count = 0
                    for container_id in container_ids:
                        # Get container health status
                        #                        cmd = ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", container_id]
                        cmd = []
                        if self.remote is not None:
                            cmd.append("ssh")
                            cmd.append(self.remote)
                        cmd.append("docker")
                        cmd.append("inspect")
                        cmd.append("--format")
                        cmd.append("{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}")
                        cmd.append(container_id)

                        try:
                            health_status = subprocess.check_output(cmd, universal_newlines=True).strip()
                            logger.debug("Container %s: Health status = %s", container_id[:12], health_status)
                            if health_status == "healthy":
                                healthy_count += 1
                        except Exception as e:
                            logger.debug("Error checking health for container %s: %s", container_id[:12], str(e))

                    logger.debug("Service %s: found %d healthy containers out of %d containers", full_service_name, healthy_count, len(container_ids))
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
        self.users = []
        self.time = []
        self.replica = []
        self.ready_replica = []
        self.util = []
        self.memory = []
        self.last_requests = None
        self.last_timestamp = None
        self.active_users = []
        
        # Aggiungi le nuove liste per Traefik
        self.traefik_incoming = []
        self.traefik_completed = []
        self.traefik_failed = []
        self.traefik_response_time = []

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
            "traefik_incoming": len(self.traefik_incoming),
            "traefik_completed": len(self.traefik_completed),
            "traefik_failed": len(self.traefik_failed),
            "traefik_response_time": len(self.traefik_response_time)
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
            "traefik_incoming": self.traefik_incoming[:min_length],
            "traefik_completed": self.traefik_completed[:min_length],
            "traefik_failed": self.traefik_failed[:min_length],
            "traefik_response_time": self.traefik_response_time[:min_length]
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
        Gets the total CPU utilization for all replicas of a specific service in a stack using cAdvisor metrics.

        Args:
            service_name (str): The name of the service (e.g., 'node')
            stack_name (str, optional): The name of the Docker Swarm stack. If None, uses self.stack_name

        Returns:
            float: The total CPU utilization as an absolute value (CPU seconds per second)
        """
        try:
            logger.debug("CPU Input parameters - service_name: '%s', stack_name: '%s'", service_name, stack_name)

            # Use provided stack_name or fall back to self.stack_name
            stack = stack_name if stack_name is not None else self.stack_name
            logger.debug("CPU Using stack name: '%s'", stack)

            # Construct the full service name using f-string
            full_service_name = f"{stack}_{service_name}"
            logger.debug("CPU Constructed full service name: '%s'", full_service_name)

            # Query for CPU usage rate over 1 minute window, summed across all replicas

            query = f'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name="{full_service_name}"}}[30s]))'
            logger.debug("CPU Prometheus query: %s", query)

            result = self.prom.custom_query(query=query)
            logger.debug("CPU Raw Prometheus result: %s", result)

            if result and len(result) > 0:
                logger.debug("%s CPU Result has data: %s", self.service_prefix, result[0])
                if 'value' in result[0]:
                    total_cpu = float(result[0]['value'][1])
                    logger.debug("CPU Extracted CPU value: %s", total_cpu)
                    return total_cpu
                else:
                    logger.debug("%s CPU No 'value' key in result[0]", self.service_prefix)
            else:
                logger.debug("%s CPU Empty or null result from Prometheus", self.service_prefix)
            return 0.0
        except Exception as e:
            logger.error("%s CPU Error collecting CPU utilization for service %s", self.service_prefix, full_service_name)
            logger.error("%s CPU Error details: %s", self.service_prefix, str(e))
            logger.error("CPU Error type: %s", type(e))
            return 0.0

    def getIncomingRequestsFromTraefik(self):
        """
        Recupera il numero di richieste in ingresso tramite Traefik.
        
        Returns:
            float: Numero di richieste in ingresso al secondo
        """
        try:
            query = 'sum(rate(traefik_service_requests_total[30s]))'
            result = self.prom.custom_query(query=query)
            
            if result and len(result) > 0 and 'value' in result[0]:
                return float(result[0]['value'][1])
            return 0
        except Exception as e:
            logger.error("Error querying Traefik incoming requests: %s", e)
            return 0

    def getCompletedRequestsFromTraefik(self):
        """
        Recupera il numero di richieste completate con successo tramite Traefik.
        
        Returns:
            float: Numero di richieste completate al secondo
        """
        try:
            query = 'sum(rate(traefik_service_requests_total{code=~"2..|3.."}[30s]))'
            result = self.prom.custom_query(query=query)
            
            if result and len(result) > 0 and 'value' in result[0]:
                return float(result[0]['value'][1])
            return 0
        except Exception as e:
            logger.error("Error querying Traefik completed requests: %s", e)
            return 0

    def getFailedRequestsFromTraefik(self):
        """
        Recupera il numero di richieste fallite tramite Traefik.
        
        Returns:
            float: Numero di richieste fallite al secondo
        """
        try:
            query = 'sum(rate(traefik_service_requests_total{code=~"4..|5.."}[30s]))'
            result = self.prom.custom_query(query=query)
            
            if result and len(result) > 0 and 'value' in result[0]:
                return float(result[0]['value'][1])
            return 0
        except Exception as e:
            logger.error("Error querying Traefik failed requests: %s", e)
            return 0

    def getResponseTimeFromTraefik(self):
        """
        Recupera il tempo di risposta medio tramite Traefik.
        
        Returns:
            float: Tempo di risposta medio in secondi
        """
        try:
            query = 'sum(rate(traefik_service_request_duration_seconds_sum[30s])) / sum(rate(traefik_service_request_duration_seconds_count[30s]))'
            result = self.prom.custom_query(query=query)
            
            if result and len(result) > 0 and 'value' in result[0]:
                return float(result[0]['value'][1])
            return 0
        except Exception as e:
            logger.error("Error querying Traefik response time: %s", e)
            return 0

    def getRequestsByService(self, service_name):
        """
        Recupera le metriche per un servizio specifico.
        
        Args:
            service_name (str): Nome del servizio (es. 'gateway')
        
        Returns:
            dict: Dizionario con metriche del servizio
        """
        try:
            metrics = {}
            
            # Richieste totali per servizio
            query = f'sum(rate(traefik_service_requests_total{{service="{service_name}"}}[30s]))'
            result = self.prom.custom_query(query=query)
            metrics['total_requests'] = float(result[0]['value'][1]) if result and len(result) > 0 else 0
            
            # Richieste completate per servizio
            query = f'sum(rate(traefik_service_requests_total{{service="{service_name}",code=~"2..|3.."}}[30s]))'
            result = self.prom.custom_query(query=query)
            metrics['completed_requests'] = float(result[0]['value'][1]) if result and len(result) > 0 else 0
            
            # Tempo di risposta per servizio
            query = f'sum(rate(traefik_service_request_duration_seconds_sum{{service="{service_name}"}}[30s])) / sum(rate(traefik_service_request_duration_seconds_count{{service="{service_name}"}}[30s]))'
            result = self.prom.custom_query(query=query)
            metrics['response_time'] = float(result[0]['value'][1]) if result and len(result) > 0 else 0
            
            return metrics
        except Exception as e:
            logger.error("Error querying Traefik metrics for service %s: %s", service_name, e)
            return {'total_requests': 0, 'completed_requests': 0, 'response_time': 0}

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
