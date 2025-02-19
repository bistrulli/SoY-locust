from locust import HttpUser, task, between, LoadTestShape
from locust import events
from locust.runners import WorkerRunner
import json
import gevent
import csv
from pathlib import Path
import time
from estimator import QNEstimaator
from controller import OPTCTRL
from estimator import Monitoring
from controller import ControlLoop
from prometheus_client import start_http_server, Counter, Summary, Gauge  # Aggiunta Gauge
import sys,argparse
import base_exp
from abc import ABC, abstractmethod
from abc import ABCMeta, abstractmethod

end=None
estimator=None
controller=None
monitor=None

# Parsing manuale degli argomenti (evita errori con Locust)
def get_custom_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", type=str, default="default_value", help="Parametro personalizzato")
    
    # Filtra solo gli argomenti non riconosciuti da Locust
    known_args, _ = parser.parse_known_args(sys.argv)

    return known_args

print(get_custom_args())

# Avvia il server Prometheus su porta 9646
start_http_server(9646)

# Metriche Prometheus
REQUEST_COUNT = Counter('locust_requests_total', 'Total number of Locust requests')
REQUEST_LATENCY = Summary('locust_request_latency_seconds', 'Request latency in seconds')
resourceDir=Path(__file__).parent.parent/Path("resources")

#qua inserisco la lettura di un file di configurazione
ctrlLoop=ControlLoop()

users=None
@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    global end, users
    end = False
    # Salva il tempo di inizio in environment se non esiste
    if not hasattr(environment, "start_time"):
        environment.start_time = time.time()
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(ctrlLoop.loop, environment)
    
    # Carica gli utenti dal file CSV solo se non sono già stati caricati
    with open(f'{resourceDir.absolute()}/soymono2/users.csv') as csv_file:
        reader = csv.DictReader(csv_file)
        users = [row for row in reader]

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    global end
    end=True

# Aggiungi una metaclasse combinata per risolvere il conflitto tra HttpUser e ABCMeta
class CombinedMeta(ABCMeta, type(HttpUser)):
    pass

# Utilizza CombinedMeta come metaclasse e imposta abstract=True per evitare che Locust istanzi questa classe
class BaseExp(HttpUser, metaclass=CombinedMeta):
    abstract = True  # Locust ignorerà questa classe
    
    wait_time = between(1, 1)
    user_index = 0  # Static variable to keep track of user index

    def on_start(self):
        global users
        # Assegna un ID univoco incrementale per ogni utente
        self.user_data = users[self.__class__.user_index % len(users)]
        self.__class__.user_index += 1

    @abstractmethod
    def userLogic(self):
        """
        Metodo astratto che deve essere implementato dalle classi specializzate.
        """
        pass

    @task
    def login_and_actions(self):
        with REQUEST_LATENCY.time():
            self.userLogic()
        REQUEST_COUNT.inc()

