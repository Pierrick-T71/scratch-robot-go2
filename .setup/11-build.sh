#!/bin/bash
# Construction de l'interface, configuree pour joindre le service du conteneur.
#
# VITE_SERVICE_URL est fige AU MOMENT DE LA CONSTRUCTION. Il doit donc pointer
# vers une adresse que le NAVIGATEUR peut atteindre, pas vers 127.0.0.1 du
# conteneur : le navigateur tourne sur ton PC, et 127.0.0.1 y designe ton PC.
set -e

export PATH="/root/go2env/bin:$PATH"
cd /root/go2/frontend

echo "=== adresse du service vue par le navigateur ==="
export VITE_SERVICE_URL="http://172.16.13.41:8765"
echo "  VITE_SERVICE_URL = $VITE_SERVICE_URL"

echo
echo "=== installation des dependances ==="
npm install --no-fund --no-audit 2>&1 | tail -5

echo
echo "=== controle de typage ==="
npm run check 2>&1 | tail -3

echo
echo "=== tests ==="
npm test 2>&1 | grep -E "Test Files|Tests " | head -2

echo
echo "=== construction ==="
npm run build 2>&1 | tail -8

echo
echo "=== contenu de dist ==="
ls -la dist/ | head -12
du -sh dist