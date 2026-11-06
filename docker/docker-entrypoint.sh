#!/bin/sh
set -e

echo "=========================================================="
echo "      Démarrage du conteneur GO2 Scratch (Alpine)        "
echo "=========================================================="

# Nettoyage et arrêt propre sur signal Docker (SIGTERM / SIGINT)
cleanup() {
    echo "Signal d'arrêt reçu : arrêt propre des services..."
    if [ -n "$NGINX_PID" ]; then
        kill -TERM "$NGINX_PID" 2>/dev/null || true
    fi
    if [ -n "$PYTHON_PID" ]; then
        kill -TERM "$PYTHON_PID" 2>/dev/null || true
    fi
    wait "$NGINX_PID" 2>/dev/null || true
    wait "$PYTHON_PID" 2>/dev/null || true
    echo "Tous les services sont arrêtés."
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

# 1. Démarrage du robot-service (FastAPI / Uvicorn)
echo "[1/2] Démarrage du backend robot-service sur le port 8765..."
cd /app/robot-service
python -m go2_service --host 0.0.0.0 --port 8765 &
PYTHON_PID=$!

# Attente brève que le service démarre
for i in $(seq 1 15); do
    if curl -s http://127.0.0.1:8765/api/status >/dev/null 2>&1; then
        echo "  -> robot-service est opérationnel !"
        break
    fi
    sleep 0.5
done

# 2. Démarrage de Nginx
echo "[2/2] Démarrage de Nginx sur les ports 80 et 5173..."
nginx -g "daemon off;" &
NGINX_PID=$!

echo "=========================================================="
echo " GO2 Scratch est prêt !"
echo "   Interface Web : http://localhost:5173 ou http://localhost:80"
echo "   API Service   : http://localhost:8765"
echo "=========================================================="

# Attente qu'un des deux processus se termine
wait -n "$PYTHON_PID" "$NGINX_PID"
cleanup
