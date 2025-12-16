import logging

import requests
logger = logging.getLogger(__name__)

def configure_autoscaler(service_name="ms-exercise",
                         stack_name="ms-stack-v5",
                         docker_compose_config="sou/monotloth-v5.yml",

                         prediction_horizon=10,
                         target_utilization=0.2,
                         control_window=20,
                         estimation_window=20,
                         measurement_period="1s",

                         output_dir="results",

                         disable_prometheus=False,
                         prom_host="192.168.3.102",
                         prom_port=9090,

                         remote_docker_host="192.168.3.102",
                         remote_docker_port=2375,
                         host="http://192.168.3.102:8081"):
    url = host.rstrip("/") + "/controllers"

    payload = {
        "service_name": service_name,
        "stack_name": stack_name,
        "sysfile": docker_compose_config,
        "control_window": control_window,
        "estimation_window": estimation_window,
        "measurement_period": measurement_period,
        "outfile": output_dir.rstrip("/") + f"/{service_name}.csv",
        "prediction_horizon": prediction_horizon,
        "target_utilization": target_utilization,
        "disable_prometheus": disable_prometheus,
        "prom_host": prom_host,
        "prom_port": prom_port,
        "remote_docker_host": remote_docker_host,
        "remote_docker_port": remote_docker_port
    }

    print("Send JSON payload to :", url)
    print(payload)
    try:
        res = requests.post(url, json=payload, timeout=5)
        res.raise_for_status()
        print("OK :", res.json())
    except requests.exceptions.RequestException as e:
        print("API Call Error :", e)
        exit(1)


def start_autoscaler(host="http://192.168.3.102:8081", service_name="ms-exercise"):
    url = host.rstrip("/") + "/controllers/" + service_name + "/start"
    print("Starting autoscaler via :", url)
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        print("OK :", res.json())
    except requests.exceptions.RequestException as e:
        print("API Call Error :", e)
        exit(1)


def stop_autoscaler(host="http://192.168.3.102:8081", service_name="ms-exercise"):
    url = host.rstrip("/") + "/controllers/" + service_name + "/stop"
    print("Stopping autoscaler via :", url)
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        print("OK :", res.json())
    except requests.exceptions.RequestException as e:
        print("API Call Error :", e)
        exit(1)
