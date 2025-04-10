#!/bin/bash

LOCUST_TIME=$1  
LOCUST_FILE=$2
STARTUSR=$3
ENDUSR=$4
STEPUSR=$5

for USERS in $(seq $STARTUSR $STEPUSR $ENDUSR); do
    echo "Executing profileapp.sh for $USERS users..."
    ./profileapp.sh $LOCUST_TIME $USERS $LOCUST_FILE
done