import sys
import os
import glob
import pandas as pd

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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rac_calculator.py <results_csv_or_directory>")
        sys.exit(1)
    path = sys.argv[1]
    theoretical_total = 420254  # Use fixed N value as provided

    if os.path.isdir(path):
        # Process all CSV files in subfolders of 'path'
        csv_files = glob.glob(os.path.join(path, "**", "*_stats.csv"), recursive=True)
        for csv_file in csv_files:
            rac_ok, rac_ko = calculate_rac(csv_file, theoretical_total)
            print(f"{csv_file}: RAC OK = {rac_ok:.4f}, RAC KO = {rac_ko:.4f}, RAC= {rac_ok+rac_ko:.4f}")
    else:
        # Single file case
        rac_ok, rac_ko = calculate_rac(path, theoretical_total)
        print(f"Request Acceptance Capability (OK): {rac_ok:.4f}")
        print(f"Request Acceptance Capability (KO): {rac_ko:.4f}")
        print(f"RAC: {rac_ok+rac_ko:.4f}")
