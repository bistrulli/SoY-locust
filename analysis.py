import numpy as np
import pandas as pd
from pathlib import Path
import glob
import re

profileDir=Path(".")

def extract_throughput_from_csv():
    # Directory dei file CSV
    csv_directory = "./profiled_data/"

    # Trova tutti i file CSV che corrispondono al pattern
    csv_files = glob.glob(csv_directory + "results_*.csv_stats.csv")

    # Dizionario per memorizzare i throughput
    throughput_data = []

    # Carica ciascun file CSV e estrai il throughput
    for file in csv_files:
        locustres = pd.read_csv(file)
        user_count=int(re.findall(r"[0-9]+",file)[0])
        throughput = locustres["Requests/s"].values[0]
        throughput_data+=[[user_count,throughput]]

    return pd.DataFrame(throughput_data,columns=["Users","Throughput"])

def calibrateQN():
	locustres=pd.read_csv(profileDir/Path("results.csv_stats.csv"))
	cpudata=pd.read_csv(profileDir/Path("cpu_utilization.csv"))
	
	troughput=locustres["Requests/s"].values[0]
	util=cpudata["CPU Utilization (%)"].mean()


	stime=(util)/troughput
	stimelct=np.sum(locustres["Average Response Time"].values[0:-1])
	print(stimelct/1000.0,(util)/(troughput*100))
	#print(stime,troughput,util)


if __name__ == '__main__':
	#calibrateQN()
    troughput_data=extract_throughput_from_csv()
    print(troughput_data.sort_values(by="Users",ascending=True))