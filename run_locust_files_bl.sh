#!/bin/bash

if [ $# -lt 1 ]; then
    echo "Use: $0 <path_loadshape_file>"
    echo "Example: $0 locust_file/loadshapes/cyclical_shape.py"
    exit 1
fi

LOADSHAPE_FILE="$1"

echo "LoadShape usage: $LOADSHAPE_FILE"
echo "Starting batch tests for all locust files..."

current_date=$(date +"%Y-%m-%d_%H-%M-%S")

#base_path="results/${current_date}"
pwd_path=$(pwd)
base_path="results"
SLEEP_TIME="3m"

REMOTE_URL="192.168.3.102"
REMOTE_PROMETHEUS_PORT=9090
REMOTE_DOCKER_PORT=2375

MEASURMENT_PERIOD="1s"
STEALTH="false"


rsync -r ../SoY-locust/ ${REMOTE_URL}:~/SoY-locust

#curl --location 'https://measure.tasul.fr/api/measure/start/6827242ad1bec86556636b28'
while read line
do
  IFS=,   read DOCKER_COMPOSE_FILENAME STACK SERVICE_NAME SPAWN_RATE NB_USERS CONTROL_WINDOWS ESTIMATION_WINDOWS BOOL_ENGINE PARAM1 PARAM2 N<<<$line
  base="${STACK}_${SPAWN_RATE}_${NB_USERS}_${BOOL_ENGINE}_${PARAM1}_${PARAM2}"
  csv_dir="${base_path}/${base}/"
  mkdir -p "${base_path}/${base}"


  #write config file
  JSON_STRING='{"service_name":"'${SERVICE_NAME}'","stack_name":"'${STACK}'","sysfile":"'${pwd_path}'/sou/'${DOCKER_COMPOSE_FILENAME}'","control_widow":'${CONTROL_WINDOWS}',"estimation_window":'${ESTIMATION_WINDOWS}',"measurament_period":"'${MEASURMENT_PERIOD}'","outfile":"test.csv","stealth":'${STEALTH}',"init_repica":'${N}',"prediction_horizon":'${PARAM2}',"target_utilization":'${PARAM1}',"prometheus":{"host":"'${REMOTE_URL}'","port":'${REMOTE_PROMETHEUS_PORT}'},"remote":"'${REMOTE_URL}'","remote_docker_port":'${REMOTE_DOCKER_PORT}'}'
  echo $JSON_STRING > /tmp/xp.json

#      curl --location 'https://measure.tasul.fr/api/measure/step/start/6827242ad1bec86556636b28?step='+$file
  echo "Execution of the test for: $STACK with spawn rate: $SPAWN_RATE, number of users: $NB_USERS, engine: $BOOL_ENGINE, param1: $PARAM1, param2: $PARAM2  (${csv_dir})"
  #python3 run_load_test.py --remote "${REMOTE_URL}" --users "${NB_USERS}" --spawn-rate "${SPAWN_RATE}" --run-time "${SLEEP_TIME}" --host "http://${REMOTE_URL}:5001" --csv "$csv_dir" --locust-file "locust_file/SoyRunner.py" --loadshape-file "$LOADSHAPE_FILE" >> "${base_path}/${base}/locust.log" 2>&1
  echo "python3 run_load_test.py --remote ${REMOTE_URL} --users ${NB_USERS} --spawn-rate ${SPAWN_RATE} --run-time ${SLEEP_TIME} --host http://${REMOTE_URL}:5001 --csv $csv_dir --locust-file locust_file/SoyRunner.py --loadshape-file $LOADSHAPE_FILE >> ${base_path}/${base}/locust.log"
  echo "Sleep for ${SLEEP_TIME} after the test"
  sleep ${SLEEP_TIME} # aggiunto per attendere 3 minuti dopo l'esecuzione del test
  echo "End of Execution of the test for: $STACK with spawn rate: $SPAWN_RATE, number of users: $NB_USERS, engine: $BOOL_ENGINE, param1: $PARAM1, param2: $PARAM2 (${csv_dir})"
#      curl --location 'https://measure.tasul.fr/api/measure/step/stop/6827242ad1bec86556636b28?step='+$file
done < listOfRuns.csv
#curl --location 'https://measure.tasul.fr/api/measure/stop/6827242ad1bec86556636b28'
