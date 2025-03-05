import sys
import os
import glob
import pandas as pd
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
    if("ctr" in results_csv):
        ctrl_data=pd.read_csv(Path(results_csv).parent/Path(f"{Path(results_csv).parent.stem}.csv"))
        rep=ctrl_data["replica"].mean()
    else:
        rep=re.findall(r"x[0-9]+",Path(results_csv).name)
        if(len(rep)!=1):
            raise ValueError(f"Error while getting replica for {Path(results_csv).name}")
        rep=int(re.findall(r"[0-9]+",rep[0])[0])
    return rep

def get_sys_troughput(results_csv):
    df = pd.read_csv(results_csv)
    df_no_last = df.iloc[:-1]  # Escludo l'ultima riga
    return df_no_last["Requests/s"].mean()
    

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
            rac_ok, rac_ko = calculate_rac(csv_file, theoretical_total)
            fr = calulate_fr(csv_file)
            efr = compute_efr(csv_file,theoretical_total)
            rt_dist=compute_rt_dist(csv_file)
            rep=getavg_avg_replica(csv_file)
            thr=get_sys_troughput(csv_file)
            res+=[[Path(csv_file).stem,rac_ok+rac_ko,fr,efr,rep,thr]+rt_dist.tolist()]

        df=pd.DataFrame(res,columns=["EXP","RAC","FR","EFR","REP","R/s","50%","75%","95%"])
        print(df)
    else:
        # Single file case
        rac_ok, rac_ko = calculate_rac(path, theoretical_total)
        print(f"Request Acceptance Capability (OK): {rac_ok:.4f}")
        print(f"Request Acceptance Capability (KO): {rac_ko:.4f}")
        print(f"RAC: {rac_ok+rac_ko:.4f}")
