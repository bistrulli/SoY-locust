import casadi
import numpy as np
import time

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
                #self.model.subject_to(T[0, i] == S[0, i] / e[i])
                #self.model.subject_to(S[0, i] <= C[i])
                #self.model.subject_to(T[0, i] <= C[i] / (e[i]))
                #self.model.subject_to(T[0, i]<= S[0, i] / e[i])
                #obj+=(C[i]-(1+tgt[i])*T[0, i])**2+0.000000*S[0, i]
                obj+=(C[i]-(tgt*T[0,i]))**2+0.0000*S[0, i]
        
            self.model.minimize(obj)    
            # self.model.solver('osqp',{'print_time':False,'error_on_fail':False})
            optionsIPOPT={'print_time':False,'ipopt':{'print_level':0}}
            optionsOSQP={'print_time':False,'osqp':{'verbose':0}}
            self.model.solver('osqp',optionsOSQP) 
        
            sol = self.model.solve()
            #(C[0]/sol.value(T),sol.value(obj),sol.value(T))
            if(nApp==1):
                return sol.value(S)
            else:
                return sol.value(S).tolist()
        else:
            return 10**(-3)
    
    def __str__(self):
        return super().__str__() + " OPTCTRL: %.2f, l: %.2f h: %.2f " % (self.step, self.l, self.h)
    
if __name__ == '__main__':
    # S=ctrl.OPTController([0.08], [0.25*0.7], [55])
    # print(S)
    import scipy.io as sio
    import numpy as np
    
    ctrl=OPTCTRL(period=1, init_cores=1, min_cores=0.1, max_cores=300, st=1)
    data=sio.loadmat("test_data.mat")
    #estimator=QNEstimaator();
    #print(data["RtLine"][:,1],data["cores"][:,1],data["users"][:,0])
    st=time.time()
    e=ctrl.estimate(data["RtLine"][0:-1,1],data["cores"][0:-1,1], data["users"][0:-1,0])
    ctime=time.time()-st;
    print(e,ctime)
    
    s=ctrl.OPTController([e], [e], [100])
    print(s)
    
    
    
        
