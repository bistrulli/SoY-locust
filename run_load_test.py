import subprocess
import argparse
from controller.controlqueuing import OPTCTRL
from estimator.monitoring import Monitoring
from estimator.qnestimator import QNEstimaator
import logging
from pathlib import Path
import signal
import sys
import os  # Nuovo import
import time

# Configura il logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
stackName = "monotloth-stack"
stackPath = Path(__file__).parent / "sou" / "monotloth-v4.yml"

# Variabile globale per salvare il processo Locust
locust_process = None


def parse_args():
    parser = argparse.ArgumentParser(description="Perform the load test with Locust")
    parser.add_argument("--users", type=int, required=True, help="Number of users (LOCUST_USERS)")
    parser.add_argument("--spawn-rate", type=int, default=100, help="User spawn speed")
    parser.add_argument("--run-time", type=str, required=True, help="Test execution time")
    parser.add_argument("--host", type=str, required=True, help="Host to test")
    parser.add_argument("--csv", type=str, required=True, help="CSV file path for the results")
    parser.add_argument("-r", "--remote", type=str, required=False, help="Remote host to test")
    parser.add_argument("-f", "--locust-file", type=str, required=True, help="Locustfile path")
    parser.add_argument("--loadshape-file", type=str, required=True,
                        help="Path of the file that defines the LoadShape to be used.")
    return parser.parse_args()


def initSys(args):
    try:
        logging.info(f"Deploying Docker Swarm leave")
        cmd = []
        if args.remote:
            cmd.append("ssh")
            cmd.append(args.remote)
        cmd.append("docker")
        cmd.append("swarm")
        cmd.append("leave")
        cmd.append("--force")
        subprocess.run(cmd, check=True)
        logging.info("Docker Swarm stack leave successfully.")
    except :

        logging.info("Docker Swarm stack leave failed.")

    logging.info(f"Deploying Docker Swarm init")
    cmd = []
    if args.remote:
        cmd.append("ssh")
        cmd.append(args.remote)
    cmd.append("docker")
    cmd.append("swarm")
    cmd.append("init")
    if args.remote:
        cmd.append("--advertise-addr")
        cmd.append(args.remote)
    subprocess.run(cmd, check=True)
    logging.info("Docker Swarm stack initiated successfully.")


def startSys(args):
    # Avvia la specifica Docker Swarm utilizzando il file sou/monotloth-v4.yml
    logging.info(f"Deploying Docker Swarm stack using {stackName}")
    cmd = []
    if args.remote:
        cmd.append("ssh")
        cmd.append(args.remote)
    cmd.append("docker")
    cmd.append("stack")
    cmd.append("deploy")
    cmd.append("--detach=true")
    cmd.append("-c")
    cmd.append(str(stackPath.absolute()))
    cmd.append(stackName)

    subprocess.run(cmd, check=True)
    logging.info("Docker Swarm stack deployed successfully.")


def stopSys(args):
    # Rimozione della stack Docker Swarm
    logging.info(f"Removing Docker Swarm stack {stackName}")
    cmd = []
    if args.remote:
        cmd.append("ssh")
        cmd.append(args.remote)
    cmd.append("docker")
    cmd.append("stack")
    cmd.append("rm")
    cmd.append(stackName)

    subprocess.run(cmd, check=True)
    logging.info("Docker Swarm stack removed successfully.")


def handle_sigint(signum, frame):
    global locust_process
    logging.info("SIGINT received. Stopping system and killing child processes...")
    if locust_process is not None:
        try:
            # Invia SIGTERM a tutto il process group
            os.killpg(os.getpgid(locust_process.pid), signal.SIGTERM)
        except Exception as e:
            logging.error(f"Error killing process group: {e}")
    stopSys()
    sys.exit(0)


# Registra il signal handler per SIGINT
signal.signal(signal.SIGINT, handle_sigint)


def main():
    global locust_process
    args = parse_args()

    # Costruzione del comando Locust in base ai parametri
    cmd = [
        "locust",
        "--headless",
        "--users", str(args.users),
        "--spawn-rate", str(args.spawn_rate),
        "--run-time", args.run_time,
        "--host", args.host,
        "--csv", args.csv,
        "-f", f"{args.locust_file},{args.loadshape_file}"  # Passa entrambi i file con una singola -f
    ]
    logging.info(" ".join(cmd))


    initSys(args)  # Deploy Docker Swarm stack
    startSys(args)  # Deploy Docker Swarm stack
    time.sleep(10)
    logging.info("Starting Locust with command:")

    # Avvia il processo in un nuovo process group
    locust_process = subprocess.Popen(
        cmd,
        preexec_fn=os.setsid
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.DEVNULL
    )
    locust_process.wait()
    logging.info("Locust execution finished.")
    stopSys(args)  # Stop della Docker Swarm stack


if __name__ == "__main__":
    main()
