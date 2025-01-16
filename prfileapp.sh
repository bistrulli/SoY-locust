#!/bin/bash

# Variables
CONTAINER_NAME="445bdc29863b"  # Replace with your container name
MONITOR_SCRIPT="getSystemUtil.py"      # Replace with the name of the Python script
INTERVAL=60                           # Interval in seconds for monitoring CPU
LOCUST_COMMAND="locust --headless --users 1 --spawn-rate 10 --run-time 1m --host http://127.0.0.1:5001 --csv results.csv -f SoyMonoShorterIfLogin.py"

# Start CPU monitoring in the background
echo "Starting CPU monitoring for container: $CONTAINER_NAME"
python3 $MONITOR_SCRIPT $CONTAINER_NAME $INTERVAL > cpu_monitor.log 2>&1 &
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

# Stop CPU monitoring
echo "Stopping CPU monitoring..."
kill $MONITOR_PID
wait $MONITOR_PID 2>/dev/null

echo "CPU monitoring stopped. Logs saved in cpu_monitor.log."
