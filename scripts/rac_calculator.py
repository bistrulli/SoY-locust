import sys
import os
import glob
import pandas as pd
import numpy as np
from pathlib import Path
import re
import matplotlib.pyplot as plt
import matplotlib
#matplotlib.use('Agg')  # Necessario per sistemi headless
from scipy import stats  # Per fitting lineare

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

def get_qnctrl_res(results_csv):
    experiment_dir = Path(results_csv).parent
    experiment_name = experiment_dir.name
    data_file = experiment_dir / f"{experiment_name}.csv"

    if not data_file.exists():
        raise ValueError(f"Errore: File dati originale {data_file} non trovato")

    return pd.read_csv(data_file)

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
        df=get_qnctrl_res(results_csv)
        
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

def create_response_time_boxplot(results_dir, output_file=None):
    """
    Crea un boxplot delle distribuzioni dei tempi di risposta di tutti gli esperimenti.
    
    Args:
        results_dir (str): Directory contenente le sottocartelle degli esperimenti
        output_file (str, optional): Path dove salvare il grafico. Se None, il grafico viene mostrato
        
    Returns:
        matplotlib.figure.Figure: L'oggetto figura creato
    """
    # Trova tutti i file dati originali (non i file stats)
    data_files = glob.glob(os.path.join(results_dir, "**", "SoyMonoShorterIfLogin_*.csv"), recursive=True)
    data_files = [f for f in data_files if not f.endswith('_stats.csv') and not f.endswith('_stats_history.csv')]
    
    if not data_files:
        print("Nessun file dati trovato per creare il boxplot")
        return None
        
    # Dizionario per memorizzare i dati dei tempi di risposta per ogni esperimento
    rt_data = {}
    
    for file_path in data_files:
        try:
            # Estrai il nome dell'esperimento dalla directory
            exp_name = Path(file_path).parent.name
            
            # Leggi il file CSV
            df = pd.read_csv(file_path)
            print(df.columns)
            
            # Verifica che la colonna 'rts' esista
            if 'rts' not in df.columns:
                print(f"Avviso: Colonna 'rts' non trovata in {file_path}, saltando...")
                continue
                
            # Filtra i valori nulli o negativi
            valid_rts = df['rts'][df['rts'] > 0]
            
            if valid_rts.empty:
                print(f"Avviso: Nessun tempo di risposta valido trovato in {file_path}, saltando...")
                continue
                
            # Memorizza i dati
            rt_data[exp_name] = valid_rts.values
            
        except Exception as e:
            print(f"Errore nella lettura del file {file_path}: {str(e)}")
    
    if not rt_data:
        print("Nessun dato valido trovato per creare il boxplot")
        return None
        
    # Crea il grafico
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Prepara i dati per il boxplot
    labels = list(rt_data.keys())
    data = [rt_data[label] for label in labels]
    
    # Ordina i dati per media crescente
    means = [np.mean(d) for d in data]
    sorted_indices = np.argsort(means)
    sorted_labels = [labels[i] for i in sorted_indices]
    sorted_data = [data[i] for i in sorted_indices]
    
    # Crea il boxplot
    bp = ax.boxplot(sorted_data, patch_artist=True, notch=True, vert=True)
    
    # Personalizza il boxplot
    for box in bp['boxes']:
        box.set(facecolor='lightblue', alpha=0.7)
    for whisker in bp['whiskers']:
        whisker.set(color='black', linewidth=1.5, linestyle='--')
    for cap in bp['caps']:
        cap.set(color='black', linewidth=2)
    for median in bp['medians']:
        median.set(color='red', linewidth=2)
    for flier in bp['fliers']:
        flier.set(marker='o', markerfacecolor='red', markersize=4, alpha=0.5)
    
    # Aggiunge titolo e etichette
    ax.set_title('Distribuzione dei Tempi di Risposta per Esperimento', fontsize=16)
    ax.set_ylabel('Tempo di Risposta (secondi)', fontsize=14)
    ax.set_xlabel('Esperimento', fontsize=14)
    
    # Imposta le etichette per l'asse x, ruotate per leggibilità
    ax.set_xticklabels(sorted_labels, rotation=45, ha='right', fontsize=10)
    
    # Aggiunge una griglia per leggibilità
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    
    # Aggiusta layout
    plt.tight_layout()
    
    # Salva o mostra il grafico
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Boxplot salvato in {output_file}")
    else:
        plt.show()
    
    return fig

def get_costs_trend(results_csv):
    """
    Fitta un modello lineare tra il tempo e la somma cumulativa delle repliche (cum_replica)
    con il vincolo che la retta deve passare per il primo e l'ultimo punto dei dati.
    
    Args:
        results_csv (str): Path al file CSV di statistiche
        
    Returns:
        tuple: (slope, intercept, r_squared)
    """
    try:
        # Usa la funzione get_cum_rep per ottenere il dataframe con la colonna cum_replica
        df_with_cum = get_cum_rep(results_csv)
        
        if df_with_cum is None:
            #print(f"Errore: Impossibile calcolare la colonna cum_replica")
            return None
            
        # Verifica che la colonna 'cum_replica' esista
        if 'cum_replica' not in df_with_cum.columns:
            #print(f"Errore: Colonna 'cum_replica' non trovata nel dataframe")
            return None
        
        # Crea un array di tempi (assumendo intervalli regolari se non esiste una colonna 'time')
        if 'time' in df_with_cum.columns:
            # Usa la colonna time esistente
            times = df_with_cum['time'].values
        else:
            # Crea array di tempi equidistanti
            times = np.arange(len(df_with_cum))
        
        # Recupera i valori della colonna cum_replica
        cum_replicas = df_with_cum['cum_replica'].values
        
        # Filtra valori nulli o non validi
        valid_indices = ~np.isnan(cum_replicas)
        valid_times = times[valid_indices]
        valid_cum_replicas = cum_replicas[valid_indices]
        
        if len(valid_times) < 2:
            #print(f"Errore: Dati insufficienti per il fitting lineare")
            return None
        
        # Prendi il primo e l'ultimo punto valido
        x1, y1 = valid_times[0], valid_cum_replicas[0]
        x2, y2 = valid_times[-1], valid_cum_replicas[-1]
        
        # Calcola la pendenza della retta che passa per questi due punti
        slope = (y2 - y1) / (x2 - x1)
        
        # Calcola l'intercetta della retta
        intercept = y1 - slope * x1
        
        # Calcola i valori predetti dal modello
        y_pred = slope * valid_times + intercept
        
        # Calcola R² manualmente
        y_mean = np.mean(valid_cum_replicas)
        r_squared = 1 - (np.sum((valid_cum_replicas - y_pred)**2) / 
                         np.sum((valid_cum_replicas - y_mean)**2))
        
        # print(f"Modello lineare vincolato per {Path(results_csv).parent.name}:")
        # print(f"Equazione: cum_replica = {slope:.6f} * t + {intercept:.6f}")
        # print(f"R²: {r_squared:.4f}")
        # print(f"Il modello passa per i punti: ({x1}, {y1}) e ({x2}, {y2})")
        
        return (slope, intercept, r_squared)
    
    except Exception as e:
        print(f"Errore durante il fitting del modello: {str(e)}")
        return None

def get_cum_rep(results_csv):
    """
    Calcola la somma cumulativa delle repliche per ogni istante temporale e 
    aggiunge questa colonna al dataframe originale.
    
    Args:
        results_csv (str): Path al file CSV di statistiche
        
    Returns:
        pandas.DataFrame: Dataframe originale con l'aggiunta della colonna 'cum_replica'
    """
    try:
        # Recupera il dataframe dei dati originali
        df = get_qnctrl_res(results_csv)
        
        # Verifica che la colonna 'replica' esista
        if 'replica' not in df.columns:
            print(f"Errore: Colonna 'replica' non trovata nel file")
            return None
        
        # Calcola la somma cumulativa delle repliche
        df['cum_replica'] = df['replica'].cumsum()
        
        #print(f"Colonna 'cum_replica' aggiunta al dataframe di {Path(results_csv).parent.name}")
        #print(f"Valore finale cumulativo: {df['cum_replica'].iloc[-1]:.2f}")
        
        return df
    
    except Exception as e:
        print(f"Errore durante il calcolo delle repliche cumulative: {str(e)}")
        return None

def plot_fitted_model(results_csv, model_results, output_file=None):
    """
    Crea un grafico che mostra i dati originali e il modello lineare vincolato 
    fittato sulla somma cumulativa delle repliche.
    
    Args:
        results_csv (str): Path al file CSV di statistiche
        model_results (tuple): Risultato della funzione get_costs_trend (slope, intercept, r_squared)
        output_file (str, optional): Path dove salvare il grafico. Se None, il grafico viene mostrato
        
    Returns:
        matplotlib.figure.Figure: L'oggetto figura creato
    """
    try:
        # Verifica che i risultati del modello siano validi
        if model_results is None:
            print("Errore: Risultati del modello non validi")
            return None
            
        slope, intercept, r_squared = model_results
        
        # Recupera i dati originali
        df_with_cum = get_cum_rep(results_csv)
        
        if df_with_cum is None:
            print("Errore: Impossibile recuperare i dati originali")
            return None
            
        # Crea un array di tempi (assumendo intervalli regolari se non esiste una colonna 'time')
        if 'time' in df_with_cum.columns:
            times = df_with_cum['time'].values
        else:
            times = np.arange(len(df_with_cum))
            
        # Recupera i valori della colonna cum_replica
        cum_replicas = df_with_cum['cum_replica'].values
        
        # Filtra valori nulli o non validi
        valid_indices = ~np.isnan(cum_replicas)
        valid_times = times[valid_indices]
        valid_cum_replicas = cum_replicas[valid_indices]
        
        # Prendi il primo e l'ultimo punto valido per evidenziarli
        x1, y1 = valid_times[0], valid_cum_replicas[0]
        x2, y2 = valid_times[-1], valid_cum_replicas[-1]
        
        # Crea il grafico
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Traccia i dati originali come scatter plot
        ax.scatter(valid_times, valid_cum_replicas, color='blue', alpha=0.6, label='Dati originali')
        
        # Evidenzia il primo e l'ultimo punto
        ax.scatter([x1, x2], [y1, y2], color='green', s=100, 
                   edgecolor='black', zorder=5, label='Punti vincolanti')
        
        # Traccia il modello lineare fittato
        x_line = np.array([min(valid_times), max(valid_times)])
        y_line = slope * x_line + intercept
        ax.plot(x_line, y_line, color='red', linewidth=2, label='Modello lineare vincolato')
        
        # Aggiungi dettagli al grafico
        experiment_name = Path(results_csv).parent.name
        ax.set_title(f'Validazione modello lineare vincolato per {experiment_name}', fontsize=16)
        ax.set_xlabel('Tempo', fontsize=14)
        ax.set_ylabel('Repliche cumulative', fontsize=14)
        
        # Aggiungi l'equazione e R² come testo nel grafico
        equation_text = f"Modello: cum_replica = {slope:.6f} * t + {intercept:.6f}\nR² = {r_squared:.4f}"
        ax.text(0.05, 0.95, equation_text, transform=ax.transAxes, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
        
        # Aggiungi una griglia per migliorare la leggibilità
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # Aggiusta i limiti se necessario per visualizzare bene i dati
        y_margin = (max(valid_cum_replicas) - min(valid_cum_replicas)) * 0.1
        ax.set_ylim(min(valid_cum_replicas) - y_margin, max(valid_cum_replicas) + y_margin)
        
        # Aggiungi legenda
        ax.legend(loc='lower right')
        
        # Aggiusta layout
        plt.tight_layout()
        
        # Salva o mostra il grafico
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"Grafico di validazione salvato in {output_file}")
        else:
            plt.show()
            
        return fig
        
    except Exception as e:
        print(f"Errore durante la creazione del grafico: {str(e)}")
        return None

def predict_cum_replicas(model_results, T):
    """
    Predice il numero cumulativo di repliche che sarebbero utilizzate
    se l'esperimento durasse T passi temporali, usando il modello lineare fittato.
    
    Args:
        model_results (tuple): Risultato della funzione get_costs_trend (slope, intercept, r_squared)
        T (int/float): Numero di passi temporali per la previsione
        
    Returns:
        float: Numero cumulativo di repliche predetto al tempo T
    """
    try:
        if model_results is None:
            #sprint("Errore: Modello non valido")
            return None
            
        slope, intercept, _ = model_results
        
        # Calcola il valore previsto usando l'equazione del modello lineare
        predicted_cum_replicas = slope * T + intercept
        
        return predicted_cum_replicas
    
    except Exception as e:
        print(f"Errore durante la previsione: {str(e)}")
        return None

def predict_cum_replicas_for_experiment(results_csv, T):
    """
    Predice il numero cumulativo di repliche per un esperimento specifico
    dopo T passi temporali.
    
    Args:
        results_csv (str): Path al file CSV di statistiche dell'esperimento
        T (int/float): Numero di passi temporali per la previsione
        
    Returns:
        tuple: (predicted_cum_replicas, model_results)
    """
    try:
        # Ottieni il modello per l'esperimento
        model_results = get_costs_trend(results_csv)
        
        if model_results is None:
            #print(f"Errore: Impossibile costruire un modello per {results_csv}")
            return None
        
        # Usa il modello per predirre il valore cumulativo a tempo T
        predicted_value = predict_cum_replicas(model_results, T)
        
        if predicted_value is not None:
            experiment_name = Path(results_csv).parent.name
            #print(f"Previsione per {experiment_name} al tempo T={T}:")
            #print(f"Repliche cumulative predette: {predicted_value:.2f}")
            
            # Recupera i dati originali per confronto
            df_with_cum = get_cum_rep(results_csv)
            if df_with_cum is not None and len(df_with_cum) > 0:
                actual_duration = len(df_with_cum)
                actual_cum_replicas = df_with_cum['cum_replica'].iloc[-1]
                #print(f"Durata effettiva dell'esperimento: {actual_duration} passi")
                #print(f"Repliche cumulative effettive: {actual_cum_replicas:.2f}")
                
                if T > actual_duration:
                    extra_duration = T - actual_duration
                    #print(f"Previsione estesa di {extra_duration} passi oltre la durata originale.")
                
        return (predicted_value, model_results)
        
    except Exception as e:
        print(f"Errore durante la previsione per l'esperimento: {str(e)}")
        return None

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
                pre_cost=predict_cum_replicas_for_experiment(csv_file,180*60)

                # Calcola l'integrale delle repliche
                replica_integral = calculate_replica_integral(csv_file)
                
                res+=[[Path(csv_file).stem,rac_ok+rac_ko,fr,
                       efr,rep,replica_integral,thr,pre_cost[0]]+rt_dist.tolist()]
            else:
                print(f"Experiment {Path(csv_file).parent.name} is not complete")

        # Calcola la pendenza del modello lineare
        df=pd.DataFrame(res,columns=["EXP","RAC","FR","EFR","REP","∫REP","R/s","PRE_COST","50%","75%","95%"])
        print(df.sort_values(by=['∫REP','50%','75%','95%'], ascending=[True, True, True, True]))
        
        # Crea il boxplot dei tempi di risposta
        # output_file = os.path.join(path, "response_time_boxplot.png")
        # create_response_time_boxplot(path, output_file)
        
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
