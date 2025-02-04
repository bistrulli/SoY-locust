import pandas as pd
import glob
import re
import numpy as np
import argparse
from pathlib import Path
import matplotlib.pyplot as plt

def extract_throughput_from_csv(profile_dir):
    # Directory dei file CSV
    csv_directory = profile_dir / "profiled_data"

    # Trova tutti i file CSV che corrispondono al pattern
    csv_files = glob.glob(str(csv_directory / "results_*.csv"))

    throughput_data = []

    # Carica ciascun file CSV e estrai il throughput
    for file in csv_files:
        locustres = pd.read_csv(file + "_stats.csv")
        user_count = int(re.findall(r"[0-9]+", file)[0])
        throughput = locustres["Requests/s"].values[0]
        throughput_data.append([user_count, throughput])

    return pd.DataFrame(throughput_data, columns=["Users", "Throughput"])

def calibrateQN(profile_dir):
    locustres = pd.read_csv(profile_dir / "results.csv_stats.csv")
    cpudata = pd.read_csv(profile_dir / "cpu_utilization.csv")

    throughput = locustres["Requests/s"].values[0]
    util = cpudata["CPU Utilization (%)"].mean()

    stime = (util) / throughput
    stimelct = np.sum(locustres["Average Response Time"].values[0:-1])
    print(stimelct / 1000.0, (util) / (throughput * 100))
    # print(stime,troughput,util)

def calculate_steady_state_throughput(users, service_time, k):
    think_time = 1  # Think time della think station
    rho = service_time / k  # Utilizzazione per server

    # Calcolo del throughput steady state
    throughput = users / (think_time + (service_time / (1 - rho)))
    return throughput

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Analisi dei risultati di Locust")
    parser.add_argument('profileDir', type=Path, help='Directory dei file di profilo')
    args = parser.parse_args()

    profile_dir = args.profileDir

    throughput_data = extract_throughput_from_csv(profile_dir)
    print(throughput_data.sort_values(by="Users", ascending=True))

    # Esempio di utilizzo della funzione calculate_steady_state_throughput
    users = 10
    service_time = 0.5
    k = 2
    steady_state_throughput = calculate_steady_state_throughput(users, service_time, k)
    print(f"Steady state throughput per {users} utenti, service time {service_time}, {k} core: {steady_state_throughput}")