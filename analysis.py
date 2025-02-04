import numpy as np
import pandas as pd
from pathlib import Path
import glob
import re
import matplotlib.pyplot as plt

profileDir=Path("./profiled_data_a")

def extract_throughput_from_csv():
	# Directory dei file CSV
	csv_directory = str(profileDir)

	# Trova tutti i file CSV che corrispondono al pattern
	csv_files = glob.glob(csv_directory + "/results_*.csv_stats.csv")

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

def calculate_steady_state_throughput(users, service_time, k):
	think_time = 1  # Think time della think station
	# Calcolo del throughput steady state
	throughput=min(users/(1/(think_time+service_time)),k/(service_time))
	return throughput


if __name__ == '__main__':
	#calibrateQN()
	troughput_data=extract_throughput_from_csv()
	troughput_data=troughput_data.sort_values(by="Users",ascending=True)
	k=1
	#pt=[calculate_steady_state_throughput(users=u, service_time=1.0/26.638775, k=1) for idx,u in enumerate(troughput_data["Users"].values)]
	for idx,u in enumerate(troughput_data["Users"].values):
		pt=calculate_steady_state_throughput(users=u, service_time=1.0/26.638775, k=k)
		mt=troughput_data.iloc[idx,1]
		print(f"User={u},Model={pt:.3f},Measured={mt:.3f},error={(pt-mt)*100/mt:.2f}%")