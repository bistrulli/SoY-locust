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
stackName="monotloth-stack"
stackPath=Path(__file__).parent/"sou"/"monotloth-v4.yml"

# Variabile globale per salvare il processo Locust
locust_process = None

def parse_args():
    parser = argparse.ArgumentParser(description="Esegui il load test con Locust")
    parser.add_argument("--users", type=int, required=True, help="Numero di utenti (LOCUST_USERS)")
    parser.add_argument("--spawn-rate", type=int, default=100, help="Velocità di spawn degli utenti")
    parser.add_argument("--run-time", type=str, required=True, help="Tempo di esecuzione del test")
    parser.add_argument("--host", type=str, required=True, help="HOST da testare")
    parser.add_argument("--csv", type=str, required=True, help="Percorso del file CSV per i risultati")
    parser.add_argument("-f", "--locust-file", type=str, required=True, help="Percorso del locustfile")
    return parser.parse_args()

def startSys():
    # Avvia la specifica Docker Swarm utilizzando il file sou/monotloth-v4.yml
    logging.info(f"Deploying Docker Swarm stack using {stackName}")
    cmd = ["docker", "stack", "deploy", "--detach=true", "-c", str(stackPath.absolute()), stackName]
    subprocess.run(cmd, check=True)
    logging.info("Docker Swarm stack deployed successfully.")

def stopSys():
    # Rimozione della stack Docker Swarm
    logging.info(f"Removing Docker Swarm stack {stackName}")
    cmd = ["docker", "stack", "rm", stackName]
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
    
    startSys()  # Deploy Docker Swarm stack
    time.sleep(5)
    logging.info("Starting Locust with command:")
    
    # Costruzione del comando Locust in base ai parametri
    cmd = [
        "locust",
        "--headless",
        "--users", str(args.users),
        "--spawn-rate", str(args.spawn_rate),
        "--run-time", args.run_time,
        "--host", args.host,
        "--csv", args.csv,
        "-f", args.locust_file
    ]
    logging.info(" ".join(cmd))
    
    # Avvia il processo in un nuovo process group e nasconde l'output in stdout e stderr
    locust_process = subprocess.Popen(
        cmd,
        preexec_fn=os.setsid,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    locust_process.wait()
    logging.info("Locust execution finished.")
    stopSys()  # Stop della Docker Swarm stack

if __name__ == "__main__":
    main()
