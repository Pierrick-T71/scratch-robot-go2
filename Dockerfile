# =======================================================
# Étape 1 : Construction du Frontend (Svelte 5 + Blockly)
# =======================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /app

# Dépendances npm du frontend
COPY frontend/package.json frontend/package-lock.json ./frontend/
# Le fichier safety-limits.json est requis par le build Vite (relatif à ../shared/)
COPY shared/ ./shared/

WORKDIR /app/frontend
RUN npm ci

# Sources et compilation statique
COPY frontend/ ./
RUN npm run build

# =======================================================
# Étape 2 : Image de Production (Debian Slim)
# =======================================================
FROM python:3.11-slim AS production

LABEL maintainer="GO2 Scratch Team"
LABEL description="Conteneur de production GO2 Scratch (Debian Slim)"

# Installation de Nginx, curl et des dépendances C requises par WebRTC / Audio / OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    curl \
    tzdata \
    gcc \
    g++ \
    portaudio19-dev \
    libasound2-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default \
    && mkdir -p /run/nginx /var/log/nginx /var/lib/nginx/html

WORKDIR /app

# Installation des dépendances Python du robot-service et du SDK WebRTC Go2
COPY robot-service/pyproject.toml ./robot-service/
RUN pip install --no-cache-dir \
    "fastapi>=0.115,<1.0" \
    "uvicorn[standard]>=0.30,<1.0" \
    "pydantic>=2.7,<3.0" \
    "unitree_webrtc_connect==2.2.0"

# Copie du code partagé et du service robot
COPY shared/ ./shared/
COPY robot-service/ ./robot-service/

# Installation du package go2-service
RUN pip install --no-cache-dir -e ./robot-service

# Copie du build statique du frontend vers Nginx
COPY --from=frontend-builder /app/frontend/dist /var/lib/nginx/html
RUN chmod -R 755 /var/lib/nginx/html

# Configuration Nginx (Reverse Proxy & HTTP Web Server)
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Script d'orchestration et point d'entrée
COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/robot-service/src

# Ports exposés :
#   - 5173 : Port standard de l'interface GO2 Scratch (Nginx)
#   - 80   : Port HTTP standard (Nginx)
#   - 8765 : Port direct du backend robot-service (FastAPI / Uvicorn)
EXPOSE 80 5173 8765

# Healthcheck de santé
HEALTHCHECK --interval=20s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8765/api/status || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
