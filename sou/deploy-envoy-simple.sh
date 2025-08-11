#!/bin/bash

set -e

echo "🚀 Deploying SoY-locust with SIMPLE Envoy proxies (NO Istio)..."

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# 1. Ferma stack esistente
log "Stopping existing stack..."
if docker stack ls | grep -q "ms-stack-v5"; then
    docker stack rm ms-stack-v5 || true
    sleep 10
    log "Waiting for cleanup..."
    sleep 20
else
    log "No existing stack found"
fi

# 2. Cleanup networks
log "Cleaning up networks..."
docker network prune -f || true

# 3. Verifica file di configurazione
log "Verifying configuration files..."
if [ ! -f "monotloth-v5-envoy-simple.yml" ]; then
    error "monotloth-v5-envoy-simple.yml not found!"
    exit 1
fi

if [ ! -f "envoy-config/gateway-envoy.yaml" ]; then
    error "envoy-config/gateway-envoy.yaml not found!"
    exit 1
fi

if [ ! -f "../prometheus/prometheus-envoy.yml" ]; then
    error "../prometheus/prometheus-envoy.yml not found!"
    exit 1
fi

if [ ! -f "monolith-v5/variables.env" ]; then
    error "monolith-v5/variables.env not found!"
    exit 1
fi

# 4. Deploy del nuovo stack SEMPLICE
log "Deploying SIMPLE Envoy-based stack..."
docker stack deploy -c monotloth-v5-envoy-simple.yml ms-stack-v5

# 5. Attendi che i servizi siano attivi
log "Waiting for services to start..."
sleep 30

# 6. Verifica stato servizi
log "Checking service status..."
docker stack services ms-stack-v5

# 7. Test di connettività
log "Testing connectivity..."
sleep 10

# Test gateway
if curl -s --max-time 10 http://localhost:8080/health > /dev/null 2>&1; then
    log "✅ Gateway is responding on http://localhost:8080"
else
    warning "❌ Gateway is not responding yet (this might be expected during startup)"
fi

# 8. Verifica metriche Envoy
log "Testing Envoy metrics collection..."
if curl -s http://localhost:15000/stats/prometheus | head -5; then
    log "✅ Gateway Envoy metrics are available"
else
    warning "❌ Gateway Envoy metrics may not be ready yet"
fi

# 9. Mostra informazioni utili
log "📊 Useful endpoints:"
echo "  - Gateway:              http://localhost:8080"
echo "  - Prometheus:           http://localhost:9090" 
echo "  - cAdvisor:             http://localhost:8081"
echo "  - Gateway Envoy Admin:  http://localhost:15000"
echo "  - ms-exercise Envoy:    http://localhost:15001"  
echo "  - ms-other Envoy:       http://localhost:15002"

log "📈 Key Envoy metrics to monitor:"
echo "  - envoy_http_inbound_*_request_total"
echo "  - envoy_http_inbound_*_request_duration_milliseconds"
echo "  - envoy_cluster_upstream_rq_*" 

log "🎯 To test the system:"
echo "  curl -X POST http://localhost:8080/api/user/login \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"test@example.com\",\"password\":\"test\"}'"

log "✅ SIMPLE Deployment completed! Stack: ms-stack-v5 with standalone Envoy proxies"
log "🔍 Monitor with: docker stack services ms-stack-v5"
log "💡 NO MORE ISTIO BULLSHIT! Just simple Envoy proxies!"