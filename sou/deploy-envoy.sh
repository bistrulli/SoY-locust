#!/bin/bash

set -e

echo "Stopping existing stack..."
docker stack rm ms-stack-v5 || true
sleep 30

echo "Cleaning networks..."
docker network prune -f

echo "Deploying stack..."
docker stack deploy -c monotloth-v5-envoy-simple.yml ms-stack-v5

echo "Waiting for services..."
sleep 30

echo "Checking services..."
docker stack services ms-stack-v5

echo "Done. Check http://localhost:8080 for gateway"