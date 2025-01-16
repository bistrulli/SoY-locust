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
        return (cpu_delta / system_cpu_delta) * 100.0 * num_cpus
    return 0.0

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
