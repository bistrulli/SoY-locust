#!/bin/bash

# Verifica se è stato fornito il parametro per il file di loadshape
if [ $# -lt 1 ]; then
    echo "Use: $0 <path_loadshape_file>"
    echo "Example: $0 locust_file/loadshapes/cyclical_shape.py"
    exit 1
fi

# Salva il percorso del file loadshape
LOADSHAPE_FILE="$1"

# Stampa informazioni sull'esecuzione
echo "LoadShape usage: $LOADSHAPE_FILE"
echo "Starting batch tests for all locust files..."

current_date=$(date +"%Y-%m-%d_%H-%M-%S")

#base_path="results/${current_date}"
base_path="results"
# Recupera tutti i file nella cartella locust_file il cui nome inizia per "SoyMonoShorterIfLogin"

curl --location 'https://measure.tasul.fr/api/measure/start/6827242ad1bec86556636b28'
for file in locust_file/SoyMonoShorterIfLogin*.py; do
    if [ -f "$file" ]; then
        # Estrae l'intero successivo alla sottostringa "_x" nel nome del file (fino a prima di .py)
        num=$(echo "$file" | grep -oP '(?<=_x).*?(?=\.py$)')
        [ -z "$num" ] && num=1  # Default se non trovato

        echo "replica to set $num"  # this correctly prints the extracted value if $num is set

        base=$(basename "$file" .py)
        # Se la cartella "${base_path}/${base}" esiste già, salta l'esperimento.
        if [ -d "${base_path}/${base}" ]; then
            echo "The folder ${base_path}/${base} already exists, skipping the experiment for $file."
            continue
        fi

        # Aggiorna il valore di replicas del servizio node in /sou/monotloth-v4.yml
        yml_file="sou/monotloth-v4.yml"
        sed -i.bak -E '/^\s*node:/,/^\s*deploy:/ { n; s/^( *replicas:)[ ]*[0-9]+/\1 '"$num"'/ }' "$yml_file"

        csv_dir="${base_path}/${base}/${base}"
        mkdir -p "${base_path}/${base}"

        curl --location 'https://measure.tasul.fr/api/measure/step/start/6827242ad1bec86556636b28?step='+$file
        echo "Execution of the test for: $file with replica $num, CSV in: $csv_dir"
        # Aggiorno il comando per passare anche il parametro loadshape-file
        python3 run_load_test.py --remote 192.168.3.102 --users 1 --spawn-rate 100 --run-time 3m --host http://192.168.3.102:5001 --csv "$csv_dir" --locust-file "$file" --loadshape-file "$LOADSHAPE_FILE" >> "${base_path}/${base}/locust.log" 2>&1
        sleep 3m # aggiunto per attendere 3 minuti dopo l'esecuzione del test
        echo "End of execution of the test for: $file with replica $num, CSV in: $csv_dir"
        curl --location 'https://measure.tasul.fr/api/measure/step/stop/6827242ad1bec86556636b28?step='+$file
    fi
done
curl --location 'https://measure.tasul.fr/api/measure/stop/6827242ad1bec86556636b28'
