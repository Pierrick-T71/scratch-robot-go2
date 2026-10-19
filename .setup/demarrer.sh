#!/bin/bash
# Demarrage de GO2 Scratch en un clic.
#
# Lance les deux processus, attend qu'ils repondent, et dit clairement si l'un
# des deux echoue. Ne s'arrete pas sur la premiere erreur : mieux vaut un
# diagnostic complet qu'un echou du milieu.

set -u

VENV=/root/go2env311
APPS=/root/go2
LOG_SERVICE="$APPS/service.log"
LOG_FRONTEND="$APPS/frontend.log"

echo "################################################"
echo "#      GO2 Scratch - demarrage"
echo "################################################"
echo

# ---------------------------------------------------------- nettoyage
echo "=== arret des processus deja lances ==="
for motif in "go2_service" "vite preview"; do
    if pkill -f "$motif" 2>/dev/null; then
        echo "  arrete : $motif"
    else
        echo "  rien a arreter : $motif"
    fi
done
sleep 2

# ------------------------------------------------------------- service
echo
echo "=== 1/2  service robot ==="
cd "$APPS/robot-service" || { echo "  repertoire introuvable"; exit 1; }
nohup "$VENV/bin/python" -m go2_service > "$LOG_SERVICE" 2>&1 &
PID_SERVICE=$!
echo "  demarre (pid $PID_SERVICE)"

attente=0
while [ $attente -lt 20 ]; do
    if "$VENV/bin/python" -c "
import urllib.request,sys
try:
    urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=2)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "  repond sur le port 8765"
        break
    fi
    sleep 1
    attente=$((attente + 1))
done
if [ $attente -ge 20 ]; then
    echo "  ECHEC : le service ne repond pas"
    echo "  --- journal ---"
    tail -20 "$LOG_SERVICE"
    ETAT=1
else
    ETAT=0
fi

# ----------------------------------------------------------- interface
echo
echo "=== 2/2  interface ==="
cd "$APPS/frontend" || { echo "  repertoire introuvable"; exit 1; }
if [ ! -d dist ]; then
    echo "  dist/ absent : construction de l'interface"
    npm run build 2>&1 | tail -3
fi
nohup npx vite preview --host 0.0.0.0 --port 5173 --strictPort \
    > "$LOG_FRONTEND" 2>&1 &
PID_FRONTEND=$!
echo "  demarre (pid $PID_FRONTEND)"

attente=0
while [ $attente -lt 25 ]; do
    if "$VENV/bin/python" -c "
import urllib.request,sys
try:
    urllib.request.urlopen('http://127.0.0.1:5173/', timeout=2)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "  repond sur le port 5173"
        break
    fi
    sleep 1
    attente=$((attente + 1))
done
if [ $attente -ge 25 ]; then
    echo "  ECHEC : l'interface ne repond pas"
    echo "  --- journal ---"
    tail -20 "$LOG_FRONTEND"
    ETAT=1
fi

# ------------------------------------------------------------ bilan
echo
echo "################################################"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "#  Adresse a ouvrir dans le navigateur :"
echo "#"
echo "#      http://${IP}:5173"
echo "#"
echo "#  service robot : http://${IP}:8765/api/status"
echo "#"
echo "#  pour arreter :  arreter-tout.sh"
echo "################################################"

echo
echo "=== ports ecoutes ==="
ss -tlnp 2>/dev/null | grep -E '8765|5173' || echo "  aucun port visible"

exit ${ETAT:-0}