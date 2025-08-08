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
    parser.add_argument('--csv', type=str, default='./', help='CSV output path')
    parser.add_argument('--locust-file', type=str, required=True, help='Locust file path')
    parser.add_argument('--loadshape-file', type=str, help='Load shape file path')
    
    # Parametro per il logging
    parser.add_argument('--log-level', type=str, default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level')
    parser.add_argument('--no-colors', action='store_true',
                       help='Disable colored output')
    
    args = parser.parse_args()
    
    # Inizializza il logging centralizzato (con colori per multi-controller)
    logger = init_logging(level=args.log_level, colored=not args.no_colors)
    
    logger.info("🔧 DEBUG MODE: Launching Locust only (assuming Docker stack is running)")
    logger.info("Target: %s", args.host)
    logger.info("Users: %d", args.users)
    logger.info("Spawn rate: %d", args.spawn_rate)
    logger.info("Duration: %s", args.run_time)
    logger.info("Locust file: %s", args.locust_file)
    if args.loadshape_file:
        logger.info("Load shape: %s", args.loadshape_file)
    logger.info("CSV output: %s", args.csv)
    logger.info("-" * 50)
    
    # Costruisce il comando Locust
    cmd = [
        'locust',
        '--headless',
        '--users', str(args.users),
        '--spawn-rate', str(args.spawn_rate),
        '--run-time', args.run_time,
        '--host', args.host,
        '--csv', args.csv
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
        # Esegue Locust
        result = subprocess.run(cmd, check=True)
        logger.info("✅ Locust completed successfully")
        
    except subprocess.CalledProcessError as e:
        logger.error("❌ Locust failed with exit code %d", e.returncode)
        sys.exit(e.returncode)
        
    except KeyboardInterrupt:
        logger.warning("⏹️ Locust interrupted by user")
        sys.exit(130)
        
    except Exception as e:
        logger.error("❌ Unexpected error: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()