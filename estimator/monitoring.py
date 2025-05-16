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
# Get service info using Docker CLI
import subprocess


class Monitoring:
    def __init__(self, window, sla, reducer=lambda x: sum(x) / len(x),
                 serviceName="", stack_name="", promHost="localhost",
                 promPort=9090, sysfile="", has_health_check=False, remote=None, remote_docker_port=None):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.serviceName = serviceName
        self.stack_name = stack_name
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
            print("Error querying Prometheus for RT:", e)
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
            print("Error querying throughput from Prometheus:", e)
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
            # print(f"[DEBUG] Attempting to get replicas for service: '{full_service_name}'")
            # print(f"[DEBUG] Available services: {[service.name for service in self.client.services.list()]}")

            service = self.client.services.get(full_service_name)
            # print(f"[DEBUG] Found service: {service.name}")
            # print(f"[DEBUG] Service attributes: {service.attrs}")

            replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
            # print(f"[DEBUG] Number of replicas: {replicas}")
            return replicas
        except docker.errors.NotFound:
            print(f"[ERROR] Service '{full_service_name}' not found.")
            return None
        except Exception as e:
            print(f"[ERROR] Error in get_replicas: {str(e)}")
            print(f"[ERROR] Error type: {type(e)}")
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

            # print(f"[DEBUG] Service {full_service_name}: found {ready_count} running replicas")

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
                            # print(f"[DEBUG] Container {container_id[:12]}: Health status = {health_status}")
                            if health_status == "healthy":
                                healthy_count += 1
                        except Exception as e:
                            print(f"[DEBUG] Error checking health for container {container_id[:12]}: {str(e)}")

                    # print(f"[DEBUG] Service {full_service_name}: found {healthy_count} healthy containers out of {len(container_ids)} containers")
                    return healthy_count
                except Exception as e:
                    print(f"[DEBUG] Error checking container health: {str(e)}")
                    # Fall back to running count
                    return ready_count
            else:
                # If no health checks, return the number of running containers
                return ready_count

        except Exception as e:
            print(f"[ERROR] Error in get_ready_replicas: {str(e)}")
            # Fallback to nominal replica count
            return self.get_replicas(stack_name, service_name)

    def reset(self):
        self.cores = []
        self.rts = []
        self.tr = []
        self.users = []
        self.time = []
        self.replica = []
        self.ready_replica = []  # Aggiungo la lista per le repliche pronte
        self.util = []
        self.memory = []
        # Aggiunta per il throughput
        self.last_requests = None
        self.last_timestamp = None
        # numero di utenti attivi cosi come visti da locust
        self.active_users = []

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
            "mem": len(self.memory)
        }

        print("###saving results##")
        print(f"Array lengths: {lengths}")

        # Trovo la lunghezza minima comune tra tutti gli array
        min_length = min(lengths.values())

        # Creo un dizionario di dati troncando ogni array alla lunghezza minima comune
        data = {
            "cores": self.cores[:min_length],
            "rts": self.rts[:min_length],
            "tr": self.tr[:min_length],
            "users": self.active_users[:min_length],
            "replica": self.replica[:min_length],
            "ready_replica": self.ready_replica[:min_length],
            "util": self.util[:min_length],
            "mem": self.memory[:min_length]
        }

        try:
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
            print(f"Data saved to {filename} (truncated to {min_length} rows)")
        except Exception as e:
            print(f"Error saving data: {e}")
            print(f"Array lengths: cores={len(self.cores)}, rts={len(self.rts)}, "
                  f"tr={len(self.tr)}, users={len(self.active_users)}, replica={len(self.replica)}, "
                  f"ready_replica={len(self.ready_replica)}, util={len(self.util)}, mem={len(self.memory)}")

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
            # print(f"[DEBUG CPU] Input parameters - service_name: '{service_name}', stack_name: '{stack_name}'")

            # Use provided stack_name or fall back to self.stack_name
            stack = stack_name if stack_name is not None else self.stack_name
            # print(f"[DEBUG CPU] Using stack name: '{stack}'")

            # Construct the full service name using f-string
            full_service_name = f"{stack}_{service_name}"
            # print(f"[DEBUG CPU] Constructed full service name: '{full_service_name}'")

            # Query for CPU usage rate over 1 minute window, summed across all replicas

            query = f'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_swarm_service_name="{full_service_name}"}}[30s]))'
            # print(f"[DEBUG CPU] Prometheus query: {query}")

            result = self.prom.custom_query(query=query)
            # print(f"[DEBUG CPU] Raw Prometheus result: {result}")

            if result and len(result) > 0:
                print(f"[DEBUG CPU] Result has data: {result[0]}")
                if 'value' in result[0]:
                    total_cpu = float(result[0]['value'][1])
                    # print(f"[DEBUG CPU] Extracted CPU value: {total_cpu}")
                    return total_cpu
                else:
                    print("[DEBUG CPU] No 'value' key in result[0]")
            else:
                print("[DEBUG CPU] Empty or null result from Prometheus")
            return 0.0
        except Exception as e:
            print(f"[ERROR CPU] Error collecting CPU utilization for service {full_service_name}")
            print(f"[ERROR CPU] Error details: {str(e)}")
            print(f"[ERROR CPU] Error type: {type(e)}")
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
