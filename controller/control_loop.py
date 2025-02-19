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
            # Se environment.runner non ha start_time, usa il valore salvato in environment.start_time
            if hasattr(environment, "shape_class") and environment.shape_class is not None:
                t = environment.shape_class.get_run_time()
            else:
                t = time.time() - (getattr(environment.runner, "start_time", environment.start_time))
            monitor.tick(t)
            print(f"### tick = {t} ###")
            # Stampa formattata in più righe
            print(f"Response Time:  {monitor.rts[-1]}\n"
                  f"Throughput:     {monitor.tr[-1]}\n"
                  f"Replicas:       {monitor.replica[-1]}\n"
                  f"Cores:          {monitor.cores[-1]}\n"
                  f"WIP:            {monitor.users[-1]}")
            if(len(monitor.rts)>self.config["estimation_window"]):
                totalcores = np.array(monitor.cores[-10:]) * np.array(monitor.replica[-10:])
                estim=estimator.estimate(np.array(monitor.rts[-10:]),
                                         totalcores,
                                         np.array(monitor.users[-10:]))
                ctrl=controller.OPTController(e=[estim], tgt=[0.05], C=[monitor.users[-1]])
                print(f"Service Time:  {estim}\n"
                      f"Replica:  {ctrl/monitor.cores[-1:]}")

            time.sleep(timeparse(self.config["control_period"]))
    
    ###L'idea è quella che in base al file di configurazione instazionio il giusto controllore
    ###Il giusto monitoring e il giusto stimatore
    def getController(self):
        '''
            TODO: parse config
        '''
        return OPTCTRL(init_cores=1, min_cores=0.1, max_cores=16, st=0.8)
    
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

