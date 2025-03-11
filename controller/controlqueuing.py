import casadi
import numpy as np
import time
import os

class OPTCTRL():
    
    def __init__(self,init_cores, min_cores, max_cores, st=0.8):
        self.init_cores=init_cores
        self.min_cores=min_cores
        self.max_cores=max_cores
        self.st=st
    
    def OPTController(self, e, tgt, C):
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
            print(C[0],e[0],sol.value(obj),sol.value(T))
            if(nApp==1):
                return sol.value(S)
            else:
                return sol.value(S).tolist()
        else:
            return 10**(-3)
    
    def OPTControllerPyomo(self, e, tgt, C):
        """
        Implementa il controllore ottimo usando pyscipopt con obiettivo linearizzato.
        
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
                print("[ERROR SCIP] Input devono essere liste o array numpy")
                return self.init_cores
                
            if len(e) == 0 or len(C) == 0 or len(tgt) == 0:
                print("[ERROR SCIP] Input lists non possono essere vuote")
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
            # diff = C_val - (1+tgt_val)*T
            #model.addCons(diff == C_val - (1+tgt_val)*T, "diff_def")
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
                print(f"[DEBUG SCIP] U={(e_val*model.getVal(T))/model.getVal(S)}, C={C_val}, e={e_val}, T={model.getVal(T)}, S={opt_value}, z={model.getVal(z)}")
                print(f"[DEBUG SCIP] term1={term1}, term2={opt_value/e_val}")
                print(f"[DEBUG SCIP] error={model.getVal(error)}, diff={model.getVal(diff)}")
                return opt_value
            else:
                print(f"[ERROR SCIP] Optimization failed: {model.getStatus()}")
                return self.init_cores

        except Exception as e:
            print(f"[ERROR SCIP] Exception in optimization: {str(e)}")
            print(f"[ERROR SCIP] Error type: {type(e)}")
            import traceback
            print(f"[ERROR SCIP] Traceback: {traceback.format_exc()}")
            return self.init_cores

    def __str__(self):
        return super().__str__() + " OPTCTRL: %.2f, l: %.2f h: %.2f " % (self.step, self.l, self.h)
    
if __name__ == '__main__':
    # S=ctrl.OPTController([0.08], [0.25*0.7], [55])
    # print(S)
    import scipy.io as sio
    import numpy as np

    def test_controllers():
        """
        Test sia OPTController che OPTControllerPyomo e confronta i risultati
        """
        # Parametri di test
        e = [0.038]      # service time
        tgt = [0.6]    # target
        C = [100]        # numero di utenti
        
        # Crea il controllore
        ctrl = OPTCTRL(init_cores=1, min_cores=0.1, max_cores=16, st=0.8)
        
        # Test OPTController originale
        print("\nTest OPTController (casadi):")
        start_time = time.time()
        s_casadi = ctrl.OPTController(e, tgt, C)
        casadi_time = time.time() - start_time
        print(f"Tempo di esecuzione casadi: {casadi_time:.4f} secondi")
        print(f"Risultato casadi: {s_casadi}")
        
        # Test OPTControllerPyomo
        print("\nTest OPTControllerSCIP (SCIP):")
        start_time = time.time()
        s_scip = ctrl.OPTControllerPyomo(e, tgt, C)
        scip_time = time.time() - start_time
        print(f"Tempo di esecuzione SCIP: {scip_time:.4f} secondi")
        print(f"Risultato SCIP: {s_scip}")
        
        # Confronto
        print("\nConfronto risultati:")
        if isinstance(s_casadi, list):
            diff = abs(s_casadi[0] - s_scip)
        else:
            diff = abs(s_casadi - s_scip)
        print(f"Differenza assoluta: {diff:.6f}")
        print(f"Speedup: {casadi_time/scip_time:.2f}x")

    # Esegui i test
    test_controllers()
    
    
    
        
