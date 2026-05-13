#!/usr/bin/env bash
# deploy.sh — unified deployment helper
# Usage:
#   ./deploy/deploy.sh local      # Docker Compose local dev
#   ./deploy/deploy.sh prod       # Docker Compose production
#   ./deploy/deploy.sh k8s        # Kubernetes
#   ./deploy/deploy.sh build      # Build Docker image only
#   ./deploy/deploy.sh stop       # Stop all containers
#   ./deploy/deploy.sh logs       # Tail logs
#   ./deploy/deploy.sh demo       # Run CLI demo in container

set -euo pipefail

IMAGE_NAME="credit-fraud-service"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-}"  # e.g. ghcr.io/yourorg or docker.io/youruser

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── build ─────────────────────────────────────────────────────────────────────
build() {
    log "Building Docker image ${IMAGE_NAME}:${IMAGE_TAG} ..."
    docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .
    if [ -n "${REGISTRY}" ]; then
        docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        log "Tagged as ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    log "Build complete."
}

# ── local dev ─────────────────────────────────────────────────────────────────
local_up() {
    log "Starting local development stack ..."
    docker compose up --build -d
    log "Waiting for services to be healthy ..."
    sleep 5
    docker compose ps
    log ""
    log "Services:"
    log "  API:        http://localhost:8000"
    log "  API docs:   http://localhost:8000/docs"
    log "  Ollama:     http://localhost:11434"
    log "  Prometheus: http://localhost:9090"
    log "  Grafana:    http://localhost:3000  (admin/admin123)"
}

# ── production ────────────────────────────────────────────────────────────────
prod_up() {
    log "Starting production stack ..."
    if [ ! -f deploy/nginx/certs/cert.pem ]; then
        warn "TLS certs not found at deploy/nginx/certs/. Generating self-signed for demo ..."
        mkdir -p deploy/nginx/certs
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout deploy/nginx/certs/key.pem \
            -out deploy/nginx/certs/cert.pem \
            -subj "/CN=fraud-api" 2>/dev/null
        log "Self-signed cert generated. Replace with real certs for production."
    fi
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    log "Production stack running."
    log "  API (via nginx): https://localhost"
}

# ── kubernetes ────────────────────────────────────────────────────────────────
k8s_deploy() {
    log "Deploying to Kubernetes ..."
    if ! command -v kubectl &>/dev/null; then
        err "kubectl not found. Install it first: https://kubernetes.io/docs/tasks/tools/"
        exit 1
    fi

    # Update image reference in deployment manifest
    if [ -n "${REGISTRY}" ]; then
        sed -i "s|credit-fraud-service:latest|${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}|g" \
            deploy/k8s/app-deployment.yaml
        log "Updated image reference to ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
    fi

    kubectl apply -f deploy/k8s/namespace.yaml
    kubectl apply -f deploy/k8s/configmap.yaml
    kubectl apply -f deploy/k8s/ollama-deployment.yaml
    kubectl apply -f deploy/k8s/app-deployment.yaml
    kubectl apply -f deploy/k8s/ingress.yaml

    log "Waiting for pods to be ready ..."
    kubectl wait --for=condition=available --timeout=300s \
        deployment/fraud-api -n fraud-detection || true

    log ""
    log "Kubernetes deployment status:"
    kubectl get pods -n fraud-detection
    kubectl get services -n fraud-detection
}

# ── stop ─────────────────────────────────────────────────────────────────────
stop() {
    log "Stopping all containers ..."
    docker compose down
    log "Done."
}

# ── logs ──────────────────────────────────────────────────────────────────────
logs() {
    docker compose logs -f app
}

# ── demo ─────────────────────────────────────────────────────────────────────
demo() {
    log "Running CLI demo in Docker container ..."
    docker run --rm \
        -e OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}" \
        "${IMAGE_NAME}:${IMAGE_TAG}" --demo
}

# ── dispatch ──────────────────────────────────────────────────────────────────
case "${1:-help}" in
    build)  build ;;
    local)  build && local_up ;;
    prod)   build && prod_up ;;
    k8s)    build && k8s_deploy ;;
    stop)   stop ;;
    logs)   logs ;;
    demo)   demo ;;
    *)
        echo ""
        echo "Usage: $0 {local|prod|k8s|build|stop|logs|demo}"
        echo ""
        echo "  local  — Docker Compose dev stack (API + Ollama + Prometheus + Grafana)"
        echo "  prod   — Docker Compose production (adds nginx TLS)"
        echo "  k8s    — Deploy to Kubernetes cluster"
        echo "  build  — Build Docker image only"
        echo "  stop   — Stop all containers"
        echo "  logs   — Tail API logs"
        echo "  demo   — Run CLI demo in container"
        echo ""
        ;;
esac
