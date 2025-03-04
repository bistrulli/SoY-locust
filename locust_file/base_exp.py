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

# Avvia il server Prometheus su porta 9646
start_http_server(9646)

end = None

# Metriche Prometheus
REQUEST_COUNT = Counter('locust_requests_total', 'Total number of Locust requests')
REQUEST_LATENCY = Summary('locust_request_latency_seconds', 'Request latency in seconds')
# Nuovo Gauge per il numero totale di utenti attivi
USER_COUNT = Gauge('locust_active_users', 'Total number of active Locust users')

resourceDir=Path(__file__).parent.parent/Path("resources")

users=None
@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    global end, users
    end = False
    # Salva il tempo di inizio in environment se non esiste
    if not hasattr(environment, "start_time"):
        environment.start_time = time.time()
    
    # Carica gli utenti dal file CSV solo se non sono già stati caricati
    with open(f'{resourceDir.absolute()}/soymono2/users.csv') as csv_file:
        reader = csv.DictReader(csv_file)
        users = [row for row in reader]

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
        # Incrementa il Gauge all'avvio dell'utente
        #USER_COUNT.inc()

    def on_stop(self):
        pass
        # Decrementa il Gauge quando l'utente termina
        #USER_COUNT.dec()

    @abstractmethod
    def userLogic(self):
        """
        Metodo astratto che deve essere implementato dalle classi specializzate.
        """
        pass

    @task
    def abstractLogic(self):
        USER_COUNT.inc()  # Incrementa all'inizio dell'esecuzione del task
        try:
            with REQUEST_LATENCY.time():
                self.userLogic()
            REQUEST_COUNT.inc()
        finally:
            USER_COUNT.dec()  # Decrementa al termine

