from estimator import QNEstimaator
from estimator import Monitoring
from controller import OPTCTRL
import time
import numpy as np
from pytimeparse.timeparse import timeparse
import docker
import logging

# Configure logging for this module
logger = logging.getLogger(__name__)

class ControlLoop():

    def __init__(self,config=None):
        self.toStop=False
        self.config=config
        self.stime=None
        self.ctrlTick=0
        self.prediction_horizon=config["prediction_horizon"]
        if config["remote"] is not None and config["remote_docker_port"] is not None:
            self.client = docker.DockerClient(base_url='tcp://'+config["remote"]+":"+str(config["remote_docker_port"]))
        else:
            self.client = docker.from_env()

        self.estimator = None
        self.controller = None
        self.monitoring = None

        self.cooldown = 3
        self.suggestion = []

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
            try:
                self.monitor.tick(t)
                logger.info("tick = %s, ctrlTick = %d", t, self.ctrlTick)

                # Verifica che tutte le liste abbiano almeno un elemento prima di accedervi
                if (len(self.monitor.rts) > 0 and len(self.monitor.tr) > 0 and
                    len(self.monitor.replica) > 0 and len(self.monitor.ready_replica) > 0 and
                    len(self.monitor.cores) > 0 and len(self.monitor.users) > 0 and
                    len(self.monitor.active_users) > 0 and len(self.monitor.util) > 0):

                    # Stampa formattata in più righe
                    logger.info("Response Time: %s", self.monitor.rts[-1])
                    logger.info("Throughput: %s", self.monitor.tr[-1])
                    logger.info("Replicas: %s", self.monitor.replica[-1])
                    logger.info("Ready Replicas: %s", self.monitor.ready_replica[-1])
                    logger.info("Cores: %s", self.monitor.cores[-1])
                    logger.info("WIP: %s", self.monitor.users[-1])
                    logger.info("WIP_prom: %s", self.monitor.active_users[-1])
                    logger.info("WIP_pred: %s", self.monitor.predict_users(horizon=self.prediction_horizon))
                    logger.info("Util: %s", self.monitor.util[-1])
                    logger.info("Mem: %s", self.monitor.memory[-1])  # Corretto: memory invece di util
                else:
                    logger.warning("Dati del monitor non ancora disponibili o incompleti nel ciclo %d", self.ctrlTick)
            except Exception as e:
                logger.error("Errore durante il ciclo di controllo: %s", str(e))
                # Continua l'esecuzione per provare nel prossimo ciclo
            if(self.ctrlTick>self.config["estimation_window"] and
               len(self.monitor.rts)>=self.config["estimation_window"]):
                totalcores = np.array(self.monitor.cores[-self.config["estimation_window"]:]) * np.array(self.monitor.replica[-self.config["estimation_window"]:])
                respnseTimes=np.array(self.monitor.rts[-self.config["estimation_window"]:])
                wip=self.monitor.predict_users(horizon=self.prediction_horizon)
                self.stime=self.monitor.util[-1]/self.monitor.tr[-1]
                stealth=self.config["stealth"]
                logger.info("Service Time: %s stealth=%s", self.stime, stealth)

            if((self.ctrlTick%self.config["control_widow"]==0) and self.stime is not None and self.stime>0):
                wip=self.monitor.predict_users(horizon=self.prediction_horizon)
                if(not self.config["stealth"]):
                    replicas=self.controller.OPTController(e=[self.stime], tgt=[self.config["target_utilization"]], C=[float(wip)])
                    self.addSuggestion(np.round(replicas))
                    logger.info("CTRL: %s", np.round(replicas))
                    self.actuate(np.round(replicas))

            time.sleep(timeparse(self.config["measurament_period"]))
            self.ctrlTick+=1

    def addSuggestion(self,replica):
        """
        Aggiunge un nuovo valore all'array circolare delle suggestioni.
        Quando l'array raggiunge la dimensione massima (self.cooldown),
        sposta tutti gli elementi a sinistra e aggiunge il nuovo valore alla fine.

        Args:
            replica (float): Valore di replica da aggiungere
        """
        if len(self.suggestion) >= self.cooldown:
            # Shift tutti gli elementi a sinistra (rimuove il primo elemento)
            # e aggiungi il nuovo valore alla fine
            self.suggestion = self.suggestion[1:] + [replica]
        else:
            # Aggiungi il valore alla fine dell'array
            self.suggestion.append(replica)

    def isDownScale(self, requested_replicas):
        """
        Determina se si tratta di downscaling confrontando le repliche richieste
        con quelle attualmente configurate nel servizio Docker.

        Args:
            requested_replicas (int): Numero di repliche richieste dal controllore

        Returns:
            bool: True se è downscaling (richieste < attuali), False altrimenti
        """
        try:
            # Construct full service name
            full_service_name = f"{self.config['stack_name']}_{self.config['service_name']}"

            # Get the service
            service = self.docker_client.services.get(full_service_name)

            # Get current number of replicas from Docker service
            current_replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)

            # It's downscaling if requested replicas are less than current replicas
            is_downscaling = requested_replicas < current_replicas
            logger.debug("Checking scaling: requested=%s, current=%s, isDownScale=%s", requested_replicas, current_replicas, is_downscaling)

            return is_downscaling
        except Exception as e:
            logger.error("Error in isDownScale: %s", str(e))
            # In case of error, assume upscaling for safety
            return False

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
                        promHost=self.config["prometheus"]["host"],
                        promPort=self.config["prometheus"]["port"],
                        sysfile=self.config["sysfile"],
                          remote=self.config["remote"],
                          remote_docker_port=self.config["remote_docker_port"],)

    def getEstimator(self):
        '''
            TODO: parse config
        '''
        return QNEstimaator()

    def actuate(self,replicas):
        """
        Aggiorna la configurazione del service monitorato impostando il numero di repliche.
        Implementa una logica differenziata: ritardo nel downscaling, risposta immediata nell'upscaling.
        """
        try:
            # Construct full service name
            full_service_name = f"{self.config['stack_name']}_{self.config['service_name']}"
            logger.debug("ACTUATE Attempting to scale service: '%s' to %d replicas", full_service_name, int(replicas))
            logger.debug("ACTUATE Available services: %s", [service.name for service in self.docker_client.services.list()])

            service = self.docker_client.services.get(full_service_name)
            logger.debug("ACTUATE Found service: %s", service.name)

            # Ottieni il numero attuale di repliche
            current_replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)

            # Verifica se si tratta di downscaling (richiesta repliche < repliche attuali)
            if self.isDownScale(int(replicas)):
                # Per il downscaling, utilizziamo il massimo delle ultime suggestioni
                # in modo da essere ancora più cauti nella riduzione delle risorse
                if len(self.suggestion) > 0:
                    # Calcola il massimo delle suggestioni, ma non scendere sotto il valore minimo
                    max_suggestion = max(self.suggestion)
                    target_replicas = max(1, int(max_suggestion))
                    logger.info("DOWNSCALING Richiesto: %d, Massimo suggestioni: %d, Target: %d", int(replicas), max_suggestion, target_replicas)
                    service.scale(target_replicas)
                else:
                    # Se non abbiamo suggestioni, usiamo il valore richiesto
                    service.scale(max(1, int(replicas)))
            else:
                # Per l'upscaling, rispondiamo immediatamente per garantire prestazioni
                # Converti replicas in int per evitare errori JSON
                service.scale(max(1, int(replicas)))
                logger.info("UPSCALING Updated service %s to %d replicas", full_service_name, int(replicas))
        except docker.errors.NotFound:
            logger.error("ACTUATE Service '%s' not found", full_service_name)
            logger.error("ACTUATE Make sure both stack_name ('%s') and service_name ('%s') are correct", self.config['stack_name'], self.config['service_name'])
        except Exception as e:
            logger.error("ACTUATE Error updating service replicas: %s", str(e))
            logger.error("ACTUATE Error type: %s", type(e))
            logger.error("ACTUATE Current config: stack_name='%s', service_name='%s'", self.config['stack_name'], self.config['service_name'])

    def saveResults(self):
        self.toStop=True
        self.monitor.save_to_csv(self.config["outfile"])
