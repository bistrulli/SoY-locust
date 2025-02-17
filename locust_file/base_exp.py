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
from prometheus_client import start_http_server, Counter,Summary
import sys,argparse
import base_exp
from abc import ABC, abstractmethod

end=None
initCore=0.1
estimator=None
controller=None
monitor=None

# Avvia il server Prometheus su porta 9646
start_http_server(9646)

# Metriche Prometheus
REQUEST_COUNT = Counter('locust_requests_total', 'Total number of Locust requests')
REQUEST_LATENCY = Summary('locust_request_latency_seconds', 'Request latency in seconds')
resourceDir=Path(__file__).parent.parent/Path("resources")

#qua inserisco la lettura di un file di configurazione
ctrlLoop=ControlLoop()

# Parsing manuale degli argomenti (evita errori con Locust)
def get_custom_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", type=str, default="default_value", help="Parametro personalizzato")
    
    # Filtra solo gli argomenti non riconosciuti da Locust
    known_args, _ = parser.parse_known_args(sys.argv)

    return known_args

#print(get_custom_args())

@events.test_start.add_listener
def on_locust_start(environment, **_kwargs):
    global end
    end = False
    # Salva il tempo di inizio in environment se non esiste
    if not hasattr(environment, "start_time"):
        environment.start_time = time.time()
    if not isinstance(environment.runner, WorkerRunner):
        gevent.spawn(ctrlLoop.loop, environment)

@events.test_stop.add_listener
def on_locust_stop(environment, **_kwargs):
    global end
    end=True

class BaseExp(HttpUser):
    wait_time = between(1, 1)
    user_index = 0  # Static variable to keep track of user index

    def on_start(self):
        # Carica gli utenti dal file CSV e assegna un utente al processo
        if not hasattr(self, 'users'):
            with open(f'{resourceDir.absolute()}/soymono2/users.csv') as csv_file:
                reader = csv.DictReader(csv_file)
                SoyMonoUser.users = [row for row in reader]

        # Assegna un ID univoco incrementale per ogni utente
        self.user_data = SoyMonoUser.users[SoyMonoUser.user_index % len(SoyMonoUser.users)]
        SoyMonoUser.user_index += 1

    def userLogic(self):
        """
        Metodo astratto che deve essere implementato dalle classi specializzate.
        """
        pass

    @task
    def login_and_actions(self):
        with REQUEST_LATENCY.time():  # Misura la latenza della richiesta
            self.userLogic()
        REQUEST_COUNT.inc()  # Incrementa il numero totale di richieste

