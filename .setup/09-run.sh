#!/bin/bash
# Lance le service en arriere-plan et interroge son etat.
VENV=/root/go2env311

echo "=== arret d'un eventuel service deja lance ==="
pkill -f "go2_service" 2>/dev/null && echo "  ancien processus arrete" || echo "  aucun processus"

cd /root/go2/robot-service || exit 1
nohup "$VENV/bin/python" -m go2_service > /root/go2/service.log 2>&1 &
echo "  demarrage (pid $!)"

sleep 7

echo
echo "=== journal ==="
tail -12 /root/go2/service.log

echo
echo "=== processus ==="
ps aux | grep -c "[g]o2_service"

echo
echo "=== ecoute ==="
ss -tlnp 2>/dev/null | grep 8765 || netstat -tlnp 2>/dev/null | grep 8765 || echo "  port 8765 non visible"