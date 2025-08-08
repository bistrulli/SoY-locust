#!/usr/bin/env python3
"""
Debug script per lanciare solo Locust senza deploy Docker Stack.
Assume che il sistema Docker sia già running.
"""

import subprocess
import argparse
import sys
from pathlib import Path

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
    
    args = parser.parse_args()
    
    print("🔧 DEBUG MODE: Launching Locust only (assuming Docker stack is running)")
    print(f"Target: {args.host}")
    print(f"Users: {args.users}")
    print(f"Spawn rate: {args.spawn_rate}")
    print(f"Duration: {args.run_time}")
    print(f"Locust file: {args.locust_file}")
    if args.loadshape_file:
        print(f"Load shape: {args.loadshape_file}")
    print(f"CSV output: {args.csv}")
    print("-" * 50)
    
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
    print("Executing command:")
    print(' '.join(cmd))
    print("-" * 50)
    
    try:
        # Esegue Locust
        result = subprocess.run(cmd, check=True)
        print("✅ Locust completed successfully")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Locust failed with exit code {e.returncode}")
        sys.exit(e.returncode)
        
    except KeyboardInterrupt:
        print("⏹️ Locust interrupted by user")
        sys.exit(130)
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()