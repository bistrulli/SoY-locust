#!/bin/bash
# Recupera tutti i file nella cartella locust_file il cui nome inizia per "SoyMonoShorterIfLogin"
for file in locust_file/SoyMonoShorterIfLogin*.py; do
    if [ -f "$file" ]; then
        # Estrae il numero che segue il carattere "x"
        num=$(grep -oP 'x\d+' "$file" | head -n1 | tr -d 'x')
        [ -z "$num" ] && num=1  # Default se non trovato

        # Aggiorna il valore di replicas del servizio node in /sou/monotloth-v4.yml
        yml_file="sou/monotloth-v4.yml"
        sed -i.bak -E "/node:/,/deploy:/{s/(replicas:)[[:space:]]*[0-9]+/\1 $num/}" "$yml_file"

        base=$(basename "$file" .py)
        csv_dir="runtime_data/${base}/${base}"
        mkdir -p "$csv_dir"
        echo "Esecuzione del test per: $file con replica $num, CSV in: $csv_dir"
        python3 run_load_test.py --users 1 --spawn-rate 100 --run-time 3m --host http://localhost:5001 --csv "$csv_dir" --locust-file "$file"
    fi
done
