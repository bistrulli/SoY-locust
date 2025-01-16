import docker
import time
import argparse

def get_cpu_delta(stats):
    """Calculate the CPU delta based on Docker stats."""
    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
    system_cpu_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']

    # Safely get the number of CPUs or default to 1
    percpu_usage = stats['cpu_stats']['cpu_usage'].get('percpu_usage', None)
    num_cpus = len(percpu_usage) if percpu_usage else 1

    if system_cpu_delta > 0 and cpu_delta > 0:
        return (cpu_delta / system_cpu_delta) * num_cpus * 100.0
    return 0.0

def get_per_cpu_utilization(stats):
    """Calculate per-CPU utilization from Docker stats."""
    percpu_usage = stats['cpu_stats']['cpu_usage'].get('percpu_usage', [])
    total_system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
    utilization = []

    if total_system_delta > 0:
        for usage in percpu_usage:
            utilization.append((usage / total_system_delta) * 100.0)

    return utilization

def get_cpu_utilization(container_name, interval):
    """Get the CPU utilization of a Docker container over a specified time window."""
    client = docker.from_env()
    container = client.containers.get(container_name)

    print(f"Monitoring CPU usage for container: {container_name}")

    try:
        start_stats = container.stats(stream=False)
        time.sleep(interval)
        end_stats = container.stats(stream=False)

        start_cpu = get_cpu_delta(start_stats)
        end_cpu = get_cpu_delta(end_stats)

        per_cpu_start = get_per_cpu_utilization(start_stats)
        per_cpu_end = get_per_cpu_utilization(end_stats)

        print(f"Per-CPU utilization at start: {per_cpu_start}")
        print(f"Per-CPU utilization at end: {per_cpu_end}")

        cpu_utilization = (start_cpu + end_cpu) / 2
        return cpu_utilization

    except docker.errors.NotFound:
        print(f"Container {container_name} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor CPU utilization of a Docker container.")
    parser.add_argument("container_name", type=str, help="Name or ID of the Docker container.")
    parser.add_argument("interval", type=float, help="Time interval (in seconds) to measure CPU utilization.")

    args = parser.parse_args()

    container_name = args.container_name
    interval = args.interval

    utilization = get_cpu_utilization(container_name, interval)
    if utilization is not None:
        print(f"CPU utilization for container '{container_name}' over {interval} seconds: {utilization:.2f}%")
