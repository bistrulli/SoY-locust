from estimator import QNEstimaator
from estimator import Monitoring
from controller import OPTCTRL
import time
import numpy as np
from pytimeparse.timeparse import timeparse

class ControlLoop():

    def __init__(self,config=None):
        self.toStop=False
        self.config=config
        self.stime=None
        self.ctrlTick=0

    '''TODO: devo ristrutturare il condice in modo tale che le misure
            vengano prese ogni secondo, la stima fatta ogni n tick e il controllo ogni m tick
    '''
    def loop(self,environment):
        global initCore, estimator, controller
        estimator=self.getEstimator()
        controller=self.getController()
        monitor=self.getMonitor()
        while not self.toStop:
            '''
                TODO: Implementare il controllo della coda
            '''
            # Ottieni il tempo corrente.
            t=self.getSimTime(environment=environment)
            monitor.tick(t)
            print(f"### tick = {t},ctrlTick = {self.ctrlTick} ###")
            # Stampa formattata in più righe
            print(f"Response Time:  {monitor.rts[-1]}\n"
                  f"Throughput:     {monitor.tr[-1]}\n"
                  f"Replicas:       {monitor.replica[-1]}\n"
                  f"Cores:          {monitor.cores[-1]}\n"
                  f"WIP:            {monitor.users[-1]}")
            if(self.ctrlTick>self.config["estimation_window"] and len(monitor.rts)>=self.config["estimation_window"]):
                totalcores = np.array(monitor.cores[-self.config["estimation_window"]:]) * np.array(monitor.replica[-self.config["estimation_window"]:])
                respnseTimes=np.array(monitor.rts[-self.config["estimation_window"]:])
                wip=np.array(monitor.users[-self.config["estimation_window"]:])
                self.stime=estimator.estimate(respnseTimes,
                                              totalcores,
                                              wip)
                print(f"Service Time:  {self.stime}")
            
            if(self.ctrlTick>self.config["control_widow"] and self.stime is not None):
                wip=np.array(monitor.users[-self.config["control_widow"]:]).mean()
                replicas=controller.OPTController(e=[self.stime], tgt=[self.stime], C=[float(wip)])
                print(f"Replica:       {replicas}")
            
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
        return Monitoring(window=30, sla=0.2,serviceName=self.config["sercice_name"],
                          promHost="localhost",promPort=9090,sysfile=self.config["sysfile"])

    def getEstimator(self):
        '''
            TODO: parse config
        '''
        return QNEstimaator()

