from estimator import QNEstimaator
from estimator import Monitoring
from controller import OPTCTRL
import time

class ControlLoop():

    toStop=None

    def __init__(self, controller,monitor,estimator):
        self.toStop=False

    def loop(environment):
        global initCore, estimator, controller
        estimator=QNEstimaator()
        controller=OPTCTRL(init_cores=initCore, min_cores=0.1, max_cores=16, st=1)
        monitor=Monitoring(window=30, sla=0.2)
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
    
