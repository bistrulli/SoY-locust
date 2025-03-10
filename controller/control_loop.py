from estimator import QNEstimaator
from estimator import Monitoring
from controller import OPTCTRL
import time
import numpy as np
from pytimeparse.timeparse import timeparse
import docker

class ControlLoop():

    def __init__(self,config=None):
        self.toStop=False
        self.config=config
        self.stime=None
        self.ctrlTick=0
        self.docker_client = docker.from_env()
        self.estimator = None
        self.controller = None
        self.monitoring = None 

    '''TODO: devo ristrutturare il condice in modo tale che le misure
            vengano prese ogni secondo, la stima fatta ogni n tick e il controllo ogni m tick
    '''
    def loop(self,environment):
        global initCore, estimator, controller
        self.estimator=self.getEstimator()
        self.controller=self.getController()
        self.monitor=self.getMonitor()
        while not self.toStop:
            # Ottieni il tempo corrente.
            t=self.getSimTime(environment=environment)
            self.monitor.tick(t)
            print(f"### tick = {t},ctrlTick = {self.ctrlTick} ###")
            # Stampa formattata in più righe
            print(f"Response Time:  {self.monitor.rts[-1]}\n"
                  f"Throughput:     {self.monitor.tr[-1]}\n"
                  f"Replicas:       {self.monitor.replica[-1]}\n"
                  f"Cores:          {self.monitor.cores[-1]}\n"
                  f"WIP:            {self.monitor.users[-1]}\n"
                  f"WIP_prom:       {self.monitor.active_users[-1]}\n"
                  f"Util:           {self.monitor.util[-1]}\n"
                  f"Mem:            {self.monitor.util[-1]}")
            if(self.ctrlTick>self.config["estimation_window"] and 
               len(self.monitor.rts)>=self.config["estimation_window"]):
                totalcores = np.array(self.monitor.cores[-self.config["estimation_window"]:]) * np.array(self.monitor.replica[-self.config["estimation_window"]:])
                respnseTimes=np.array(self.monitor.rts[-self.config["estimation_window"]:])
                #wip=np.array(self.monitor.users[-self.config["estimation_window"]:])
                wip=np.array(self.monitor.active_users[-self.config["estimation_window"]:])
                # self.stime=self.estimator.estimate(respnseTimes,
                #                               totalcores,
                #                               wip)
                #print(f"stime1={self.stime},stime2={self.monitor.util[-1]/self.monitor.tr[-1]}")
                #self.stime=0.095
                self.stime=self.monitor.util[-1]/self.monitor.tr[-1]
                stealth=self.config["stealth"]
                print(f"Service Time:  {self.stime} stealth={stealth}")
            
            if((self.ctrlTick%self.config["control_widow"]==0) and self.stime>0):
                #wip=np.array(self.monitor.users[-self.config["control_widow"]:]).mean()
                wip=np.array(self.monitor.active_users[-self.config["control_widow"]:]).mean()
                print("Cristo")
                if(not self.config["stealth"]):
                    replicas=self.controller.OPTController(e=[self.stime], tgt=[(self.stime+1)], C=[float(wip)])
                    print(f"CTRL:          {np.ceil(replicas)}")
                    self.actuate(replicas=np.ceil(replicas))
            
            time.sleep(timeparse(self.config["measurament_period"]))
            self.ctrlTick+=1
    
    ###L'idea è quella che in base al file di configurazione instazionio il giusto controllore
    ###Il giusto monitoring e il giusto stimatore
    def getController(self):
        '''
            TODO: parse config
        '''
        return OPTCTRL(init_cores=1, min_cores=0.1, max_cores=16, st=0.8)

    def getSimTime(self,environment):
         # Ottieni il tempo corrente.
        # Se environment.runner non ha start_time, usa il valore salvato in environment.start_time
        if hasattr(environment, "shape_class") and environment.shape_class is not None:
            t = environment.shape_class.get_run_time()
        else:
            t = time.time() - (getattr(environment.runner, "start_time", environment.start_time))

        return t
    
    def getMonitor(self):
        '''
            TODO: parse config
        '''
        return Monitoring(window=self.config["measurament_period"], 
                        sla=0.2,
                        serviceName=self.config["service_name"],
                        stack_name=self.config["stack_name"],
                        promHost="localhost",
                        promPort=9090,
                        sysfile=self.config["sysfile"])

    def getEstimator(self):
        '''
            TODO: parse config
        '''
        return QNEstimaator()

    def actuate(self, replicas):
        """
        Aggiorna la configurazione del service monitorato impostando il numero di repliche.
        """
        try:
            service_name = self.config["service_name"]
            service = self.docker_client.services.get(service_name)
            # Converti replicas in int per evitare errori JSON
            service.scale(int(replicas))
            print(f"Updated service {service_name} to {int(replicas)} replicas.")
        except Exception as e:
            print(f"Error updating service replicas: {e}")

    def saveResults(self):
        self.toStop=True
        self.monitor.save_to_csv(self.config["outfile"])