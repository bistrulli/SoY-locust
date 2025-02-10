import docker
import time
import argparse
import csv
from datetime import datetime
import signal
import sys
import subprocess
import json

def get_cpu_delta(stats):
    """Calculate the CPU delta based on Docker stats."""
    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
    system_cpu_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']

    if system_cpu_delta > 0 and cpu_delta > 0:
        num_cpus = len(stats['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
        return (cpu_delta / system_cpu_delta) * num_cpus * 100.0
    return 0.0

def get_docker_cpu_usage_cli(container_name):
    try:
        # Command as a list to avoid shell=True
        command = [
            "docker", 
            "stats", 
            container_name, 
            "--no-stream", 
            "--format", 
            "{{json .}}"
        ]
        # Run the command and capture the output
        result = subprocess.check_output(command, text=True).strip()
        
        # Parse the result as JSON
        stats = json.loads(result)
        cpu_usage = stats.get("CPUPerc", "0%").strip('%')
        return float(cpu_usage)
    except subprocess.CalledProcessError as e:
        print(f"Error while running docker stats: {e}")
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {e}")
    return None

def signal_handler(sig, frame):
    """Handle SIGINT signal to gracefully terminate the script."""
    print("\nMonitoring stopped by SIGINT signal.")
    sys.exit(0)

def get_cpu_utilization(container_names, interval, csv_file):
    """Get the CPU utilization of a Docker container over a specified time window and save to a CSV file."""
    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Timestamp", "CPU Utilization (%)", "Num Cpus"])

        try:
            while True:
                timestamp = datetime.now().isoformat()
                #num_cpus = len(stats['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
                total_cpu_utilization = 0.0
                for container_name in container_names:
                    total_cpu_utilization +=get_docker_cpu_usage_cli(container_name)

                writer.writerow([timestamp, total_cpu_utilization])
                print(f"{timestamp} - CPU Utilization: {total_cpu_utilization:.2f}%")

                time.sleep(interval)

        except docker.errors.NotFound:
            print(f"Container {container_name} not found.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor CPU utilization of a Docker container and save to CSV.")
    parser.add_argument("container_names", nargs='+', help="Name or ID of the Docker container.")
    parser.add_argument("interval", type=float, help="Time interval (in seconds) to measure CPU utilization.")
    parser.add_argument("csv_file", type=str, help="Path to the CSV file for saving results.")

    args = parser.parse_args()

    container_names = args.container_names
    interval = args.interval
    csv_file = args.csv_file

    # Register the SIGINT handler
    signal.signal(signal.SIGINT, signal_handler)

    get_cpu_utilization(container_names, interval, csv_file)
