#!/usr/bin/env python3
"""
Debug script per lanciare solo Locust senza deploy Docker Stack.
Assume che il sistema Docker sia già running.
"""

import subprocess
import argparse
import sys
from pathlib import Path
from setup_logging import init_logging

def main():
    parser = argparse.ArgumentParser(description="Debug Locust launcher - no Docker deployment")
    
    # Parametri essenziali per Locust
    parser.add_argument('--users', '--user', type=int, default=1, help='Number of users')
    parser.add_argument('--spawn-rate', type=int, default=1, help='Spawn rate')
    parser.add_argument('--run-time', type=str, default='1m', help='Run time (e.g., 3m)')
    parser.add_argument('--host', type=str, required=True, help='Target host URL')
    parser.add_argument('--csv', type=str, default=None, help='CSV output base path (prefix). If omitted, uses results/<locust-file>/<locust-file>')
    parser.add_argument('--locust-file', type=str, required=True, help='Locust file path')
    parser.add_argument('--loadshape-file', type=str, help='Load shape file path')
    parser.add_argument('--logfile', type=str, default=None, help='Locust logfile path. If omitted, uses results/<locust-file>/<locust-file>.log')
    
    # Parametro per il logging
    parser.add_argument('--log-level', type=str, default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    parser.add_argument('--no-colors', action='store_true',
                       help='Disable colored output')
    
    args = parser.parse_args()
    
    # Per Locust, il logging verrà configurato automaticamente da base_exp.py
    # Qui usiamo un logger semplice solo per i messaggi di debug dello script
    import logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s [%(levelname)5s] %(message)s',
        datefmt='%H:%M:%S'
    )
    logger = logging.getLogger(__name__)

    # Calcolo del percorso CSV di default se non specificato
    locust_name = Path(args.locust_file).stem
    if args.csv:
        raw_csv = Path(args.csv)
        # Se è una directory o termina con separatore, usa quella dir e aggiungi il nome base
        if str(args.csv).endswith(('/', '\\')) or raw_csv.is_dir():
            csv_dir = raw_csv
            csv_dir.mkdir(parents=True, exist_ok=True)
            csv_base = str(csv_dir / locust_name)
        else:
            # Tratta come prefisso base. Se termina con .csv, rimuovi estensione
            if str(raw_csv).lower().endswith('.csv'):
                raw_csv = raw_csv.with_suffix('')
            parent_dir = raw_csv.parent
            if str(parent_dir):
                parent_dir.mkdir(parents=True, exist_ok=True)
            csv_base = str(raw_csv)
    else:
        csv_dir = Path('results') / locust_name
        csv_dir.mkdir(parents=True, exist_ok=True)
        csv_base = str(csv_dir / locust_name)
    # Calcolo del logfile di default se non specificato
    if args.logfile:
        logfile_path = args.logfile
    else:
        locust_name = Path(args.locust_file).stem
        log_dir = Path('results') / locust_name
        log_dir.mkdir(parents=True, exist_ok=True)
        logfile_path = str(log_dir / f"{locust_name}.log")
    
    logger.info("🔧 DEBUG MODE: Launching Locust only (assuming Docker stack is running)")
    logger.info("Target: %s", args.host)
    logger.info("Users: %d", args.users)
    logger.info("Spawn rate: %d", args.spawn_rate)
    logger.info("Duration: %s", args.run_time)
    logger.info("Locust file: %s", args.locust_file)
    if args.loadshape_file:
        logger.info("Load shape: %s", args.loadshape_file)
    logger.info("CSV output: %s", csv_base)
    logger.info("📁 Locust logs: %s", logfile_path)
    logger.info("-" * 50)
    
    # Costruisce il comando Locust
    cmd = [
        'locust',
        '--headless',
        '--users', str(args.users),
        '--spawn-rate', str(args.spawn_rate),
        '--run-time', args.run_time,
        '--host', args.host,
        '--csv', csv_base,
        '--loglevel', args.log_level,
        '--logfile', logfile_path
    ]
    
    # Aggiunge i file
    locust_files = [args.locust_file]
    if args.loadshape_file:
        locust_files.append(args.loadshape_file)
    
    cmd.extend(['-f', ','.join(locust_files)])
    
    # Mostra il comando che verrà eseguito
    logger.info("Executing command:")
    logger.info(' '.join(cmd))
    logger.info("-" * 50)
    
    try:
        # Esegue Locust e cattura output per diagnosi in caso di errore
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("✅ Locust completed successfully")
        if result.stdout:
            logger.debug(result.stdout)
        if result.stderr:
            logger.debug(result.stderr)
        
    except subprocess.CalledProcessError as e:
        logger.error("❌ Locust failed with exit code %d", e.returncode)
        try:
            if e.stdout:
                logger.error("[locust stdout]\n%s", e.stdout)
            if e.stderr:
                logger.error("[locust stderr]\n%s", e.stderr)
        except Exception:
            pass
        sys.exit(e.returncode)
        
    except KeyboardInterrupt:
        logger.warning("⏹️ Locust interrupted by user")
        sys.exit(130)
        
    except Exception as e:
        logger.error("❌ Unexpected error: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()