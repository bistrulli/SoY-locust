#!/bin/bash

set -e

echo "🚀 Deploying SoY-locust with Istio service mesh..."

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funzione per logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# 1. Ferma lo stack esistente se presente
log "Stopping existing stack..."
if docker stack ls | grep -q "ms-stack-v5"; then
    docker stack rm ms-stack-v5 || true
    sleep 10
    log "Waiting for complete cleanup..."
    sleep 20
else
    log "No existing stack found"
fi

# 2. Cleanup networks if needed
log "Cleaning up networks..."
docker network prune -f || true

# 3. Verifica file di configurazione
log "Verifying configuration files..."
if [ ! -f "monotloth-v5-istio.yml" ]; then
    error "monotloth-v5-istio.yml not found!"
    exit 1
fi

if [ ! -f "istio-config/mesh.yaml" ]; then
    error "istio-config/mesh.yaml not found!"
    exit 1
fi

if [ ! -f "../prometheus/prometheus-istio.yml" ]; then
    error "../prometheus/prometheus-istio.yml not found!"
    exit 1
fi

if [ ! -f "monolith-v5/variables.env" ]; then
    error "monolith-v5/variables.env not found!"
    exit 1
fi

# 4. Deploy del nuovo stack
log "Deploying Istio-based stack..."
docker stack deploy -c monotloth-v5-istio.yml ms-stack-v5

# 5. Attendi che tutti i servizi siano attivi
log "Waiting for services to start..."
sleep 30

# 6. Verifica stato servizi
log "Checking service status..."
docker stack services ms-stack-v5

# 7. Attendi che Istio Control Plane sia pronto
log "Waiting for Istio Control Plane to be ready..."
timeout=300
counter=0
while [ $counter -lt $timeout ]; do
    if docker exec $(docker ps -q --filter "name=ms-stack-v5_istio-pilot") curl -s http://localhost:15014/ready | grep -q "LIVE"; then
        log "✅ Istio Control Plane is ready!"
        break
    fi
    sleep 5
    counter=$((counter + 5))
    if [ $((counter % 30)) -eq 0 ]; then
        warning "Still waiting for Istio Control Plane... ($counter/$timeout seconds)"
    fi
done

if [ $counter -ge $timeout ]; then
    error "Istio Control Plane failed to become ready within $timeout seconds"
    exit 1
fi

# 8. Verifica che i sidecar siano connessi
log "Checking Envoy sidecar status..."
sleep 10

for sidecar in gateway-sidecar ms-exercise-sidecar ms-other-sidecar; do
    if docker ps --filter "name=ms-stack-v5_$sidecar" --format "table {{.Names}}\t{{.Status}}" | grep -q "Up"; then
        log "✅ $sidecar is running"
    else
        warning "❌ $sidecar is not running properly"
    fi
done

# 9. Test di connettività
log "Testing connectivity..."
sleep 5

# Test gateway
if curl -s --max-time 10 http://localhost:8080/health > /dev/null 2>&1; then
    log "✅ Gateway is responding on http://localhost:8080"
else
    warning "❌ Gateway is not responding yet (this might be expected during startup)"
fi

# 10. Verifica metriche Prometheus
log "Testing Prometheus metrics collection..."
if curl -s http://localhost:9090/api/v1/targets | grep -q "envoy"; then
    log "✅ Prometheus is collecting Envoy metrics"
else
    warning "❌ Prometheus may not be collecting Envoy metrics yet"
fi

# 11. Mostra informazioni utili
log "📊 Useful endpoints:"
echo "  - Gateway:           http://localhost:8080"
echo "  - Prometheus:        http://localhost:9090" 
echo "  - cAdvisor:          http://localhost:8081"
echo "  - Gateway Envoy:     http://localhost:15000 (admin)"
echo "  - ms-exercise Envoy: http://localhost:15001 (admin)"
echo "  - ms-other Envoy:    http://localhost:15002 (admin)"

log "📈 Key Envoy metrics to monitor:"
echo "  - envoy_http_inbound_*_request_total"
echo "  - envoy_http_inbound_*_request_duration_milliseconds" 
echo "  - envoy_cluster_upstream_rq_*"
echo "  - envoy_server_memory_allocated"

log "🎯 To test the system:"
echo "  curl -X POST http://localhost:8080/api/user/login \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"test@example.com\",\"password\":\"test\"}'"

log "✅ Deployment completed! Stack: ms-stack-v5 with Istio service mesh"
log "🔍 Monitor with: docker stack services ms-stack-v5"