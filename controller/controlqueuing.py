import casadi
import numpy as np
import time
import os
import logging
import traceback
import math

# Configure logging for this module
logger = logging.getLogger(__name__)

class OPTCTRL():
    
    def __init__(self,init_cores, min_cores, max_cores, st=0.8):
        self.init_cores=init_cores
        self.min_cores=min_cores
        self.max_cores=max_cores
        self.st=st
    
    def OPTControllerCasadi(self, e, tgt, C):
        """
        Implementa il controllore ottimo usando CasADi (versione legacy).
        
        Args:
            e (list): Service time attuale
            tgt (list): Service time target
            C (list): Numero di utenti attivi
        
        Returns:
            float o list: Numero ottimo di repliche
        """
        #print("stime:=", e, "tgt:=", tgt, "user:=", C)
        if(np.sum(C)>0):
            self.model = casadi.Opti("conic") 
            #self.model = casadi.Opti() 
            nApp = len(tgt)
            
            T = self.model.variable(1, nApp);
            S = self.model.variable(1, nApp);

            self.model.subject_to(T >= 0)
            self.model.subject_to(self.model.bounded(self.min_cores, S, self.max_cores))
            
            obj=0;
            for i in range(nApp):
                self.model.subject_to(T[0, i] == casadi.fmin(C[i] / (1.0+e[i]),S[0, i] / e[i]))
                #self.model.subject_to(e[i]*T[0, i]<=0.20*S[0, i])
                #self.model.subject_to(T[0, i] == S[0, i] / e[i])
                #self.model.subject_to(S[0, i] <= C[i])
                #self.model.subject_to(T[0, i] <= C[i] / (e[i]))
                #self.model.subject_to(T[0, i]<= S[0, i] / e[i])
                #obj+=(C[i]-(1+tgt[i])*T[0, i])**2+0.000000*S[0, i]
                obj+=(e[i]*T[0, i]-0.20*S[0, i])**2
        
            self.model.minimize(obj)    
            # self.model.solver('osqp',{'print_time':False,'error_on_fail':False})
            optionsIPOPT={'print_time':False,'ipopt':{'print_level':0,"max_iter": 5000}}
            optionsOSQP={'print_time':False,'osqp':{'verbose':0}}
            self.model.solver('osqp',optionsOSQP) 
        
            sol = self.model.solve()
            logger.debug("CASADI C=%s, e=%s, obj=%s, T=%s", C[0], e[0], sol.value(obj), sol.value(T))
            if(nApp==1):
                return sol.value(S)
            else:
                return sol.value(S).tolist()
        else:
            return 10**(-3)
    
    def OPTController(self, e, tgt, C):
        """
        Implementa il controllore ottimo usando SCIP.
        
        Args:
            e (list): Service time attuale
            tgt (list): Service time target
            C (list): Numero di utenti attivi
        
        Returns:
            float: Numero ottimo di repliche
        """
        try:
            from pyscipopt import Model, quicksum
            import numpy as np

            # Validazione input
            if not isinstance(e, (list, np.ndarray)) or not isinstance(C, (list, np.ndarray)) or not isinstance(tgt, (list, np.ndarray)):
                logger.error("SCIP Input devono essere liste o array numpy")
                return self.init_cores
                
            if len(e) == 0 or len(C) == 0 or len(tgt) == 0:
                logger.error("SCIP Input lists non possono essere vuote")
                return self.init_cores

            if np.sum(C) <= 0:
                return 10**(-3)

            # Estrai i valori scalari per il caso single-app
            e_val = float(e[0])
            C_val = float(C[0])
            tgt_val = float(tgt[0])

            # Crea il modello SCIP
            model = Model("controller")
            model.hideOutput()  # Disabilita l'output

            # Variabili decisionali
            S = model.addVar("S", lb=self.min_cores, ub=self.max_cores)
            T = model.addVar("T", lb=0)  # Throughput
            z = model.addVar("z", vtype="B")  # Variabile binaria per il min
            
            # Variabile ausiliaria per linearizzare l'obiettivo
            error = model.addVar("error", lb=0)  # Errore assoluto
            diff = model.addVar("diff", lb=-C_val, ub=C_val)  # Differenza

            # Calcola i due termini del min
            term1 = C_val/(1.0 + e_val)  # C[i]/(1+e[i])

            # Big-M sufficientemente grande
            M = max(self.max_cores/e_val, C_val) * 2

            # Vincoli per implementare T = min(term1, term2) usando big-M
            # Se z = 1, T = term1; se z = 0, T = term2
            model.addCons(T <= term1, "bound1")
            model.addCons(T <= S/e_val, "bound2")
            model.addCons(T >= term1 - M*(1-z), "bound3")
            model.addCons(T >= S/e_val - M*z, "bound4")

            # Vincoli per linearizzare l'obiettivo quadratico
            model.addCons(diff == e_val*T-tgt[0]*S, "diff_def")
            
            # error >= |diff| usando due vincoli lineari
            model.addCons(error >= diff, "error_bound1")
            model.addCons(error >= -diff, "error_bound2")

            # Funzione obiettivo linearizzata
            model.setObjective(error - T, "minimize")

            # Risolvi
            model.setRealParam('limits/time', 60)  # Limite di tempo in secondi
            model.optimize()

            # Verifica la soluzione
            if model.getStatus() == "optimal":
                opt_value = model.getVal(S)
                logger.debug("U=%s, C=%s, e=%s, T=%s, S=%s, z=%s", (e_val*model.getVal(T))/model.getVal(S), C_val, e_val, model.getVal(T), opt_value, model.getVal(z))
                logger.debug("term1=%s, term2=%s", term1, opt_value/e_val)
                logger.debug("error=%s, diff=%s", model.getVal(error), model.getVal(diff))
                return opt_value
            else:
                logger.error("Optimization failed: %s", model.getStatus())
                return self.init_cores

        except Exception as e:
            logger.error("Exception in optimization: %s", str(e))
            logger.error("Error type: %s", type(e))
            import traceback
            logger.error("Traceback: %s", traceback.format_exc())
            return self.init_cores


class OpenClassCTRL:
    """
    Controllore per queuing centers aperti basato su teoria delle code.
    Ogni servizio è modellato come M/M/S queue con:
    - λ (arrival rate) misurato da nginx-vts  
    - μ (service rate) = 1/service_time stimato
    - S (repliche) calcolato per mantenere utilizzo target
    
    Formula: S = ceil(λ * service_time / target_utilization)
    """
    
    def __init__(self, min_replicas=1, max_replicas=16):
        """
        Inizializza il controllore per queuing center aperto.
        
        Args:
            min_replicas (int): Numero minimo di repliche
            max_replicas (int): Numero massimo di repliche
        """
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        logger.debug("OpenClassCTRL initialized: min=%d, max=%d", min_replicas, max_replicas)
    
    def calculate_replicas(self, arrival_rate, service_time, target_utilization):
        """
        Calcola il numero ottimo di repliche per queuing center aperto.
        
        Modello: M/M/S queue
        - λ: arrival rate (req/sec)
        - μ: service rate per replica = 1/service_time (req/sec/replica)  
        - ρ: utilizzo per replica = λ/(μ*S) = λ*service_time/S
        - Stabilità: ρ < 1 → λ < μ*S
        
        Formula ottima: S = ceil(λ * service_time / target_utilization)
        
        Args:
            arrival_rate (float): Arrival rate predetto (richieste/secondo)
            service_time (float): Service time stimato (secondi/richiesta)
            target_utilization (float): Utilizzo target per replica (0.0-1.0)
        
        Returns:
            int: Numero ottimo di repliche
        """
        try:
            # Validazione input
            if arrival_rate <= 0:
                logger.debug("Arrival rate <= 0, returning min replicas")
                return self.min_replicas
                
            if service_time <= 0:
                logger.warning("Service time <= 0 (%.4f), returning min replicas", service_time)
                return self.min_replicas
                
            if target_utilization <= 0 or target_utilization >= 1:
                logger.warning("Invalid target utilization %.4f, using 0.8", target_utilization)
                target_utilization = 0.8
            
            # Formula queuing theory: S = ceil(λ * service_time / target_utilization)
            optimal_replicas_float = (arrival_rate * service_time) / target_utilization
            optimal_replicas = math.ceil(optimal_replicas_float)
            
            # Applica bounds
            bounded_replicas = max(self.min_replicas, min(optimal_replicas, self.max_replicas))
            
            # Calcola utilizzo effettivo con repliche scelte
            actual_utilization = (arrival_rate * service_time) / bounded_replicas
            service_rate_per_replica = 1.0 / service_time
            total_service_rate = service_rate_per_replica * bounded_replicas
            
            logger.debug("OpenClass: λ=%.4f, μ=%.4f, service_time=%.4f, tgt_util=%.3f", 
                        arrival_rate, service_rate_per_replica, service_time, target_utilization)
            logger.debug("OpenClass: optimal_float=%.2f → ceil=%d → bounded=%d", 
                        optimal_replicas_float, optimal_replicas, bounded_replicas)
            logger.debug("OpenClass: actual_util=%.3f, stability=%.3f (λ/total_μ)", 
                        actual_utilization, arrival_rate/total_service_rate)
            
            return bounded_replicas
            
        except Exception as e:
            logger.error("Error in OpenClassCTRL: %s", str(e))
            logger.error("Params: λ=%.4f, service_time=%.4f, tgt=%.3f", 
                        arrival_rate, service_time, target_utilization)
            return self.min_replicas
    
    def __str__(self):
        return f"OpenClassCTRL(min={self.min_replicas}, max={self.max_replicas})"

    def __str__(self):
        return super().__str__() + " OPTCTRL: %.2f, l: %.2f h: %.2f " % (self.step, self.l, self.h)
    
if __name__ == '__main__':
    def test_controllers():
        """
        Test sia OPTControllerCasadi che OPTController e confronta i risultati
        """
        # Parametri di test
        e = [0.038]      # service time
        tgt = [0.6]    # target
        C = [100]        # numero di utenti
        
        # Crea il controllore
        ctrl = OPTCTRL(init_cores=1, min_cores=0.1, max_cores=16, st=0.8)
        
        # Test OPTControllerCasadi
        logger.info("Test OPTControllerCasadi (legacy):")
        start_time = time.time()
        s_casadi = ctrl.OPTControllerCasadi(e, tgt, C)
        casadi_time = time.time() - start_time
        logger.info("Tempo di esecuzione casadi: %.4f secondi", casadi_time)
        logger.info("Risultato casadi: %s", s_casadi)
        
        # Test OPTController
        logger.info("Test OPTController (SCIP):")
        start_time = time.time()
        s_scip = ctrl.OPTController(e, tgt, C)
        scip_time = time.time() - start_time
        logger.info("Tempo di esecuzione SCIP: %.4f secondi", scip_time)
        logger.info("Risultato SCIP: %s", s_scip)
        
        # Confronto
        logger.info("Confronto risultati:")
        if isinstance(s_casadi, list):
            diff = abs(s_casadi[0] - s_scip)
        else:
            diff = abs(s_casadi - s_scip)
        logger.info("Differenza assoluta: %.6f", diff)
        logger.info("Speedup: %.2fx", casadi_time/scip_time)

    # Esegui i test
    test_controllers()
    
    
    
        
