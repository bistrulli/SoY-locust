import numpy as np
import pandas as pd
from pathlib import Path

profileDir=Path("profiled_data")

def calibrateQN():
	locustres=pd.read_csv(profileDir/Path("results.csv_stats.csv"))
	cpudata=pd.read_csv(profileDir/Path("cpu_utilization.csv"))
	
	troughput=locustres[locustres["Name"]=="/api/exercise-production"]["Requests/s"].values
	util=cpudata["CPU Utilization (%)"].mean()


	stime=util/troughput
	print(stime,np.sum(locustres["Average Response Time"].values[0:-1]))


if __name__ == '__main__':
	calibrateQN()