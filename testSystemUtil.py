import docker
import time

def get_container_cpu_usage(container_id):
    client = docker.from_env()
    container = client.containers.get(container_id)

    stats_stream = container.stats(decode=True)
    prev_stats = next(stats_stream)

    # Wait a moment for the next stats snapshot
    time.sleep(1)
    current_stats = next(stats_stream)

    # Calculate CPU usage
    cpu_delta = current_stats['cpu_stats']['cpu_usage']['total_usage'] - prev_stats['cpu_stats']['cpu_usage']['total_usage']
    system_delta = current_stats['cpu_stats']['system_cpu_usage'] - prev_stats['cpu_stats']['system_cpu_usage']
    number_cpus = len(current_stats['cpu_stats']['cpu_usage'].get('percpu_usage', [])) or 1

    if system_delta > 0 and cpu_delta > 0:
        cpu_usage_percentage = (cpu_delta / system_delta) #* number_cpus * 100.0
        return cpu_usage_percentage
    else:
        return 0.0

if __name__ == '__main__':
    # Example usage
    container_id = "aa3819696c7f"  # Replace with your container ID or name
    while(True):
        cpu_usage = get_container_cpu_usage(container_id)
        print(f"CPU Usage: {cpu_usage:.2f}%")
        time.sleep(1)