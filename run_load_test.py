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
import importlib.util

# Configura il logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Variabili globali che verranno impostate dinamicamente
stackName = None
stackPath = None

# Variabile globale per salvare il processo Locust
locust_process = None


def load_config_from_locust_file(locust_file_path):
    """
    Carica la configurazione dal file locust specificato.
    
    Args:
        locust_file_path (str): Percorso del file locust
        
    Returns:
        tuple: (stack_name, stack_path)
        
    Raises:
        ValueError: Se la configurazione non è valida
        ImportError: Se il file locust non può essere caricato
    """
    try:
        # Carica il file locust come modulo
        spec = importlib.util.spec_from_file_location("locust_module", locust_file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load locust file: {locust_file_path}")
        
        locust_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(locust_module)
        
        # Verifica che exp_conf esista
        if not hasattr(locust_module, 'exp_conf'):
            raise ValueError(f"Locust file must contain 'exp_conf' configuration dictionary: {locust_file_path}")
        
        exp_conf = locust_module.exp_conf
        
        # Verifica che stack_name esista
        if 'stack_name' not in exp_conf:
            raise ValueError(f"exp_conf must contain 'stack_name' configuration in: {locust_file_path}")
        
        # Verifica che sysfile esista
        if 'sysfile' not in exp_conf:
            raise ValueError(f"exp_conf must contain 'sysfile' path configuration in: {locust_file_path}")
        
        stack_name = exp_conf['stack_name']
        sysfile_path = exp_conf['sysfile']
        
        # Verifica che il file di sistema esista
        if not Path(sysfile_path).exists():
            raise ValueError(f"System file path specified in exp_conf['sysfile'] does not exist: {sysfile_path}")
        
        return stack_name, Path(sysfile_path)
        
    except ImportError as e:
        raise ImportError(f"Failed to load locust file {locust_file_path}: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error loading configuration from {locust_file_path}: {str(e)}")


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
    # Avvia la specifica Docker Swarm utilizzando il file configurato
    if stackName is None or stackPath is None:
        logging.error("Cannot start system: stack name or path not configured")
        return
        
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
    if stackName is None:
        logging.error("Cannot stop system: stack name not configured")
        return
        
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
    # Create a dummy args object for stopSys
    class DummyArgs:
        pass
    dummy_args = DummyArgs()
    dummy_args.remote = None
    stopSys(dummy_args)
    sys.exit(0)


# Registra il signal handler per SIGINT
signal.signal(signal.SIGINT, handle_sigint)


def main():
    global locust_process, stackName, stackPath
    args = parse_args()

    # Carica la configurazione dal file locust
    try:
        stackName, stackPath = load_config_from_locust_file(args.locust_file)
        logging.info(f"Loaded configuration from locust file: stack_name='{stackName}', sysfile='{stackPath}'")
    except (ValueError, ImportError) as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

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
