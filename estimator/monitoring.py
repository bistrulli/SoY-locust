from pathlib import Path
from config import locustDataDir,serviceName
import pasndas as pd
import numpy as np
import docker

class Monitoring:
    def __init__(self, window, sla, reducer=lambda x: sum(x)/len(x)):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.reset()

    def tick(self, t):
        for i in range(1, len(self.time)+1):
            if t - self.time[-i] > self.window:
                try:
                    del self.rts[-i]
                    del self.users[-i]
                except:
                    break
        
        self.time+=[t]
        self.rts+=[self.getRT()]
        self.tr+=[self.getTroughput()]
        self.users+=[self.getUsers()]
        self.cores+=[self.getCores()]

    def getUsers(self):
        #logica per misurare il numero di utenti dal file di locust
        if not len(self.users): return 0
        return self.reducer(self.users)

    def getRT(self):
        #logica per misurare il tempo di risposta dal file di locust
        if not len(self.rts): return 0
        return self.reducer(self.rts)

    def getTroughput(self):
        #logica per misurare il throughput dal file di locust
        pass

    def getUtil(self):
        #logica per misurare l'utilizzo da docker
        pass

    def get_replicas(self,service_name):
        try:
            service = self.client.services.get(service_name)
            replicas = service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 1)
            return replicas
        except docker.errors.NotFound:
            print(f"Service '{service_name}' not found.")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def getViolations(self):
        def appendViolation(rts):
            if self.reducer(rts) > self.sla:
                return 1
            else:
                return 0
        second = int(self.time[0])
        violations = []
        rts = []
        
        for (t, rt) in zip(self.time, self.allRts):
            if int(t) != second:
                violations.append(appendViolation(rts))
                rts = []
                second = int(t)
            rts.append(rt)
        violations.append(appendViolation(rts))
        return sum(violations)
        
    def reset(self):
        self.client = docker.from_env()
        self.allRts = []
        self.allUsers = []
        self.allCores = []
        self.rts = []
        self.tr = []
        self.users = []
        self.time = []