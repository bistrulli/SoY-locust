#!/bin/bash

#get name of running container
# Get container IDs excluding 'monotlothv4_postgres' and store them in an array
container_ids=$(docker ps --format "{{.ID}} {{.Names}}" | grep -v "monotlothv4_postgres" | awk '{print $1}')

echo "Container IDs: ${container_ids[@]}"

# Variables
#CONTAINER_NAME="monotloth-v4-node-1"  # Replace with your container name
CONTAINER_NAME=${container_ids[0]}
MONITOR_SCRIPT="getSystemUtil.py"      # Replace with the name of the Python script
INTERVAL=1                           # Interval in seconds for monitoring CPU
LOCUST_TIME=$1
LOCUST_USERS=$2
LOCUST_FILE=$3
HOST=http://localhost:5001
CSV_FILE="./profiled_data/cpu_utilization_$LOCUST_USERS.csv"       # Output CSV file for CPU utilization
LOCUST_COMMAND="locust --headless --users $LOCUST_USERS --spawn-rate 100 --run-time $LOCUST_TIME --host $HOST --csv ./profiled_data/results_$LOCUST_USERS.csv -f $LOCUST_FILE"

# Start CPU monitoring in the background
echo "Starting CPU monitoring for container: $CONTAINER_NAME"
python3 $MONITOR_SCRIPT $CONTAINER_NAME $INTERVAL $CSV_FILE > cpu_monitor.log 2>&1 &
MONITOR_PID=$!
echo "CPU monitoring process started with PID: $MONITOR_PID"

# Start Locust
echo "Starting Locust..."
$LOCUST_COMMAND

# Wait for Locust to finish
LOCUST_EXIT_CODE=$?
if [ $LOCUST_EXIT_CODE -eq 0 ]; then
    echo "Locust completed successfully."
else
    echo "Locust encountered an error with exit code $LOCUST_EXIT_CODE."
fi

# Send SIGINT to the monitoring process (equivalent to Ctrl+C)
echo "Stopping CPU monitoring..."
kill -INT $MONITOR_PID
wait $MONITOR_PID 2>/dev/null

echo "CPU monitoring stopped. Logs saved in cpu_monitor.log. CPU usage data saved in $CSV_FILE."
