import subprocess
import argparse
from controller.controlqueuing import OPTCTRL
from estimator.monitoring import Monitoring
from estimator.qnestimator import QNEstimaator

def parse_args():
    parser = argparse.ArgumentParser(description="Esegui il load test con Locust")
    parser.add_argument("--users", type=int, required=True, help="Numero di utenti (LOCUST_USERS)")
    parser.add_argument("--spawn-rate", type=int, default=100, help="Velocità di spawn degli utenti")
    parser.add_argument("--run-time", type=str, required=True, help="Tempo di esecuzione del test")
    parser.add_argument("--host", type=str, required=True, help="HOST da testare")
    parser.add_argument("--csv", type=str, required=True, help="Percorso del file CSV per i risultati")
    parser.add_argument("-f", "--locust-file", type=str, required=True, help="Percorso del locustfile")
    return parser.parse_args()

def main():
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
        "--enable-prometheus",
        "--web-port=","8089",
        "-f", args.locust_file
    ]
    subprocess.call(cmd)

if __name__ == "__main__":
    main()
