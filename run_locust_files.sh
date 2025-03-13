#!/bin/bash

# Verifica se è stato fornito il parametro per il file di loadshape
if [ $# -lt 1 ]; then
    echo "Utilizzo: $0 <path_loadshape_file>"
    echo "Esempio: $0 locust_file/loadshapes/cyclical_shape.py"
    exit 1
fi

# Salva il percorso del file loadshape
LOADSHAPE_FILE="$1"

# Stampa informazioni sull'esecuzione
echo "Utilizzo LoadShape: $LOADSHAPE_FILE"
echo "Avvio dei test batch per tutti i file locust..."

# Recupera tutti i file nella cartella locust_file il cui nome inizia per "SoyMonoShorterIfLogin"
for file in locust_file/SoyMonoShorterIfLogin*.py; do
    if [ -f "$file" ]; then
        # Estrae l'intero successivo alla sottostringa "_x" nel nome del file (fino a prima di .py)
        num=$(echo "$file" | grep -oP '(?<=_x).*?(?=\.py$)')
        [ -z "$num" ] && num=1  # Default se non trovato

        echo "replica to set $num"  # questo stampa correttamente il valore estratto se $num è impostato

        base=$(basename "$file" .py)
        # Se la cartella "results/${base}" esiste già, salta l'esperimento.
        if [ -d "results/${base}" ]; then
            echo "La cartella results/${base} esiste già, salto l'esperimento per $file."
            continue
        fi

        # Aggiorna il valore di replicas del servizio node in /sou/monotloth-v4.yml
        yml_file="sou/monotloth-v4.yml"
        sed -i.bak -E '/^\s*node:/,/^\s*deploy:/ { n; s/^( *replicas:)[ ]*[0-9]+/\1 '"$num"'/ }' "$yml_file"

        csv_dir="results/${base}/${base}"
        mkdir -p "results/${base}"
        echo "Esecuzione del test per: $file con replica $num, CSV in: $csv_dir"
        
        # Aggiorno il comando per passare anche il parametro loadshape-file
        python3 run_load_test.py --users 1 --spawn-rate 100 --run-time 3m --host http://localhost:5001 --csv "$csv_dir" --locust-file "$file" --loadshape-file "$LOADSHAPE_FILE" >> "results/${base}/locust.log" 2>&1
        sleep 3m # aggiunto per attendere 3 minuti dopo l'esecuzione del test
    fi
done
