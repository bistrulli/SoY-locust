import docker
import time
import argparse
import csv
from datetime import datetime
import signal
import sys

def get_cpu_delta(stats):
    """Calculate the CPU delta based on Docker stats."""
    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
    system_cpu_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']

    if system_cpu_delta > 0 and cpu_delta > 0:
        return (cpu_delta / system_cpu_delta) * 100.0
    return 0.0

def signal_handler(sig, frame):
    """Handle SIGINT signal to gracefully terminate the script."""
    print("\nMonitoring stopped by SIGINT signal.")
    sys.exit(0)

def get_cpu_utilization(container_name, interval, csv_file):
    """Get the CPU utilization of a Docker container over a specified time window and save to a CSV file."""
    client = docker.from_env()
    container = client.containers.get(container_name)

    print(f"Monitoring CPU usage for container: {container_name}")

    with open(csv_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Timestamp", "CPU Utilization (%)"])

        try:
            while True:
                start_stats = container.stats(stream=False)
                time.sleep(interval)
                end_stats = container.stats(stream=False)

                start_cpu = get_cpu_delta(start_stats)
                end_cpu = get_cpu_delta(end_stats)

                num_cpus = len(end_stats['cpu_stats']['cpu_usage'].get('percpu_usage', [1]))
                cpu_utilization = ((start_cpu + end_cpu) / 2) * num_cpus

                timestamp = datetime.now().isoformat()
                writer.writerow([timestamp, cpu_utilization])
                print(f"{timestamp} - CPU Utilization: {cpu_utilization:.2f}%")

        except docker.errors.NotFound:
            print(f"Container {container_name} not found.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor CPU utilization of a Docker container and save to CSV.")
    parser.add_argument("container_name", type=str, help="Name or ID of the Docker container.")
    parser.add_argument("interval", type=float, help="Time interval (in seconds) to measure CPU utilization.")
    parser.add_argument("csv_file", type=str, help="Path to the CSV file for saving results.")

    args = parser.parse_args()

    container_name = args.container_name
    interval = args.interval
    csv_file = args.csv_file

    # Register the SIGINT handler
    signal.signal(signal.SIGINT, signal_handler)

    get_cpu_utilization(container_name, interval, csv_file)
