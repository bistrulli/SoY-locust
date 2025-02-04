import numpy as np
import pandas as pd
from pathlib import Path

profileDir=Path(".")

def calibrateQN():
	locustres=pd.read_csv(profileDir/Path("results.csv_stats.csv"))
	cpudata=pd.read_csv(profileDir/Path("cpu_utilization.csv"))
	
	troughput=locustres[locustres["Name"]=="/"]["Requests/s"].values
	util=cpudata["CPU Utilization (%)"].mean()


	stime=(util)/troughput
	stimelct=np.sum(locustres["Average Response Time"].values[0:-1])
	#print(troughput[0]*(stimelct)/1000.0,(util)/(troughput*100))
	print(stime,troughput,util)


if __name__ == '__main__':
	calibrateQN()