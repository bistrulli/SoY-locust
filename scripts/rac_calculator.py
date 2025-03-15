import sys
import os
import glob
import pandas as pd
import numpy as np
from pathlib import Path
import re

def calculate_rac(results_csv, theoretical_total):
    # Legge il file CSV aggregato contenente dati dal file SoyMonoShorterIfLogin_*_stats.csv
    df = pd.read_csv(results_csv)
    df_no_last = df.iloc[:-1]  # Escludo l'ultima riga
    #print(df_no_last["Request Count"])
    ok_requests = df_no_last['Request Count'].sum()      # Somma delle richieste OK
    ko_requests = df_no_last['Failure Count'].sum()       # Somma delle richieste KO
    rac_ok = ok_requests / theoretical_total
    rac_ko = ko_requests / theoretical_total
    return rac_ok, rac_ko

def calulate_fr(results_csv):
    df = pd.read_csv(results_csv)
    df_no_last = df.iloc[:-1]  # Escludo l'ultima riga
    #print(df_no_last["Request Count"])
    ok_requests = df_no_last['Request Count'].sum()      # Somma delle richieste OK
    ko_requests = df_no_last['Failure Count'].sum()       # Somma delle richieste KO
    fr=ko_requests/(ko_requests+ok_requests)
    
    return fr

def compute_efr(results_csv, theoretical_total):
    df = pd.read_csv(results_csv)
    df_no_last = df.iloc[:-1]  # Escludo l'ultima riga
    ko_requests = df_no_last['Failure Count'].sum()       # Somma delle richieste KO
    efr=ko_requests/(theoretical_total)
    return efr

def compute_rt_dist(results_csv):
    df = pd.read_csv(results_csv)
    df_no_last = df.iloc[:-1]  # Escludo l'ultima riga
    return df_no_last[["50%","75%","95%"]].sum()

def getavg_avg_replica(results_csv):
    rep=None
    cumRep=None

    #history file
    parent_dir = Path(results_csv).parent.name  # Nome della directory contenente il file
    history=pd.read_csv(Path(results_csv).parent/f"{parent_dir}_stats_history.csv")
    start=history["Timestamp"].min()
    end=history["Timestamp"].max()
    duration=end-start

    if("ctr" in results_csv):
        ctrl_data=pd.read_csv(Path(results_csv).parent/f"{parent_dir}.csv")
        rep=ctrl_data["replica"].mean()
        cumRep=ctrl_data["replica"].sum()
    else:
        rep=re.findall(r"x[0-9]+",Path(results_csv).name)
        if(len(rep)!=1):
            raise ValueError(f"Error while getting replica for {Path(results_csv).name}")
        rep=int(re.findall(r"[0-9]+",rep[0])[0])
        cumRep=duration*rep
    return rep,cumRep

def get_sys_troughput(results_csv):
    df = pd.read_csv(results_csv)
    df_no_last = df.iloc[:-1]  # Escludo l'ultima riga
    return df_no_last["Requests/s"].mean()

def is_complete(results_csv):
    resPath=Path(results_csv)
    return (resPath.parent/f"{resPath.parent.name}.csv").exists()

def calculate_replica_integral(results_csv):
    """
    Calcola l'integrale numerico della colonna "replica" nel file CSV originale 
    associato al file di statistiche fornito.
    Utilizza il metodo dei trapezi per l'integrazione numerica.
    
    Args:
        results_csv (str): Path al file CSV di statistiche (es. *_stats.csv)
        
    Returns:
        float: Valore dell'integrale numerico delle repliche
    """
    try:
        # Determino il percorso del file dati originale
        experiment_dir = Path(results_csv).parent
        experiment_name = experiment_dir.name
        data_file = experiment_dir / f"{experiment_name}.csv"
        
        if not data_file.exists():
            print(f"Errore: File dati originale {data_file} non trovato")
            return 0.0
            
        # Leggi il file CSV originale
        df = pd.read_csv(data_file)
        
        # Verifica che la colonna "replica" esista
        if 'replica' not in df.columns:
            print(f"Errore: La colonna 'replica' non esiste nel file {data_file}")
            return 0.0
        
        # Estrai i valori di replica
        replicas = df['replica'].values
        
        # Se il file contiene timestamp, usali per una migliore approssimazione
        if 'Timestamp' in df.columns:
            timestamps = df['Timestamp'].values
            # Converti i timestamp in secondi se necessario
            if isinstance(timestamps[0], str):
                timestamps = pd.to_datetime(timestamps).astype(np.int64) // 10**9
            
            # Calcola l'integrale usando il metodo dei trapezi con i timestamp
            integral = np.trapezoid(replicas, timestamps)
        else:
            # Altrimenti, assume punti equidistanti (1 secondo tra ogni misurazione)
            # Calcola l'integrale usando il metodo dei trapezi con intervalli di 1
            integral = np.trapezoid(replicas)
        
        return integral
    
    except Exception as e:
        print(f"Errore durante il calcolo dell'integrale per {results_csv}: {str(e)}")
        return 0.0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rac_calculator.py <results_csv_or_directory>")
        sys.exit(1)
    path = sys.argv[1]
    theoretical_total = 420254  # Use fixed N value as provided

    if os.path.isdir(path):
        # Process all CSV files in subfolders of 'path'
        csv_files = glob.glob(os.path.join(path, "**", "*_stats.csv"), recursive=True)
        res=[]
        for csv_file in csv_files:
            if(is_complete(csv_file)):
                rac_ok, rac_ko = calculate_rac(csv_file, theoretical_total)
                fr = calulate_fr(csv_file)
                efr = compute_efr(csv_file,theoretical_total)
                rt_dist=compute_rt_dist(csv_file)
                rep,cumRep=getavg_avg_replica(csv_file)
                thr=get_sys_troughput(csv_file)
                
                # Calcola l'integrale delle repliche
                replica_integral = calculate_replica_integral(csv_file)
                
                res+=[[Path(csv_file).stem,rac_ok+rac_ko,fr,
                       efr,rep,replica_integral,thr]+rt_dist.tolist()]
            else:
                print(f"Experiment {Path(csv_file).parent.name} is not complete")

        df=pd.DataFrame(res,columns=["EXP","RAC","FR","EFR","REP","∫REP","R/s","50%","75%","95%"])
        print(df.sort_values(by=['95%', '75%', '50%','∫REP'], ascending=[True, True, True, True]))
    else:
        # Single file case
        rac_ok, rac_ko = calculate_rac(path, theoretical_total)
        print(f"Request Acceptance Capability (OK): {rac_ok:.4f}")
        print(f"Request Acceptance Capability (KO): {rac_ko:.4f}")
        print(f"RAC: {rac_ok+rac_ko:.4f}")
        
        # If it's a stats file, try to find the corresponding data file for replica integral
        if "_stats.csv" in path:
            replica_integral = calculate_replica_integral(path)
            print(f"Replica Integral: {replica_integral:.4f}")
