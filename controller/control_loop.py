from estimator import QNEstimaator
from estimator import Monitoring
from controller import OPTCTRL
import time

class ControlLoop():

    def __init__(self,config=None):
        self.toStop=False
        self.config=config

    def loop(self,environment):
        global initCore, estimator, controller
        estimator=self.getEstimator()
        controller=self.getController()
        monitor=self.getMonitor()
        while not set.toStop:
            '''
                TODO: Implementare il controllo della coda
            '''
            # Ottieni il tempo corrente.
            # Se environment.runner non ha start_time, usa il valore salvato in environment.start_time
            if hasattr(environment, "shape_class") and environment.shape_class is not None:
                t = environment.shape_class.get_run_time()
            else:
                t = time.time() - (getattr(environment.runner, "start_time", environment.start_time))
            print(f"###tick={t}###")
            monitor.tick(t)
            time.sleep(1)
    
    def getController(self):
        '''
            TODO: parse config
        '''
        return OPTCTRL(init_cores=1, min_cores=0.1, max_cores=16, st=1)
    
    def getMonitor(self):
        '''
            TODO: parse config
        '''
        return Monitoring(window=30, sla=0.2)

    def getEstimator(self):
        '''
            TODO: parse config
        '''
        return QNEstimaator()
    
