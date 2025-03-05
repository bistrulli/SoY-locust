#!/bin/bash
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
        python3 run_load_test.py --users 1 --spawn-rate 100 --run-time 3m --host http://localhost:5001 --csv "$csv_dir" --locust-file "$file" >> "results/${base}/locust.log" 2>&1
        sleep 3m # aggiunto per attendere 1 minuto dopo l'esecuzione del test
    fi
done
