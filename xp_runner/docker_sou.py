import subprocess
import logging
import time

logger = logging.getLogger(__name__)


def deploy_stack(stack_name="ms-stack-v5",
                 docker_compose_config="sou/monotloth-v5.yml",
                 remote_docker_host=None,
                 remote_docker_port=2375, ):
    try:
        cmd = ["docker", "stack", "deploy", "-c", docker_compose_config, stack_name]
        env = {}
        if remote_docker_host is not None:
            env["DOCKER_HOST"] = "tcp://" + remote_docker_host + ":" + str(remote_docker_port)
        print(cmd)
        subprocess.run(cmd, env=env, check=True)
        logging.info("Docker Swarm stack leave successfully.")
        time.sleep(25)
    except:
        logging.info("Docker Swarm stack leave failed.")
        exit(1)


def remove_stack(stack_name="ms-stack-v5",
                 remote_docker_host=None,
                 remote_docker_port=2375, ):
    try:
        cmd = ["docker", "stack", "rm", stack_name]
        env = {}
        if remote_docker_host is not None:
            env["DOCKER_HOST"] = "tcp://" + remote_docker_host + ":" + str(remote_docker_port)
        subprocess.run(cmd, env=env, check=True)
        logging.info("Docker Swarm stack removed successfully.")
    except:
        logging.info("Docker Swarm stack removal failed.")
        exit(1)


def scale_service(
        stack_name="ms-stack-v5",
        service_name="ms-exercise",
        replicas=3,
        remote_docker_host=None,
        remote_docker_port=2375, ):
    try:
        cmd = ["docker", "service", "scale", stack_name + "_" + service_name + "=" + str(replicas)]
        env = {}
        if remote_docker_host is not None:
            env["DOCKER_HOST"] = "tcp://" + remote_docker_host + ":" + str(remote_docker_port)
        print(cmd)
        print(env)
        subprocess.run(cmd, env=env, check=True)
        logging.info(f"Service {service_name} scaled to {replicas} replicas successfully.")
        time.sleep(5)
    except:
        logging.info(f"Scaling service {service_name} failed.")
        exit(1)


def cp_stack_logs(
        result_folder="results",
        stack_name="ms-stack-v5",
        service_name="auto-scaler",
        remote_docker_host=None,
        remote_docker_port=2375, ):
    try:
        cmd = ["docker", "ps", "--format", "'{{.Names}}'"]
        env = {}
        if remote_docker_host is not None:
            env["DOCKER_HOST"] = "tcp://" + remote_docker_host + ":" + str(remote_docker_port)
        res = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            line = line.replace("'", "")
            if line.startswith(stack_name + "_" + service_name):
                id_docker_container = line.strip().strip("'")
                cmd = ["docker", "cp", id_docker_container + ":/logs/", result_folder.rstrip()+"/logs/"]
                env = {}
                if remote_docker_host is not None:
                    env["DOCKER_HOST"] = "tcp://" + remote_docker_host + ":" + str(remote_docker_port)
                subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
                cmd = ["docker", "cp", id_docker_container + ":/results/", result_folder.rstrip()+"/results/"]
                env = {}
                if remote_docker_host is not None:
                    env["DOCKER_HOST"] = "tcp://" + remote_docker_host + ":" + str(remote_docker_port)
                subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
                break
    except:
        logging.info(f"Copying service {stack_name} failed.")
        exit(1)
