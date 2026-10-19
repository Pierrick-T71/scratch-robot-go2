#!/bin/bash
# Interface servie depuis le conteneur, sur toutes les interfaces.
set -e
export PATH="/root/go2env/bin:$PATH"

echo "=== arret des services precedents ==="
pkill -f "go2_service" 2>/dev/null && echo "  service arrete" || echo "  pas de service"
pkill -f "vite preview" 2>/dev/null && echo "  interface arretee" || echo "  pas d'interface"

echo
echo "=== redemarrage du service robot ==="
cd /root/go2/robot-service
nohup /root/go2env311/bin/python -m go2_service > /root/go2/service.log 2>&1 &
sleep 6
tail -3 /root/go2/service.log

echo
echo "=== demarrage de l'interface ==="
cd /root/go2/frontend
nohup npx vite preview --host 0.0.0.0 --port 5173 --strictPort \
    > /root/go2/frontend.log 2>&1 &
sleep 8
tail -8 /root/go2/frontend.log

echo
echo "=== ports ecoutes ==="
ss -tlnp 2>/dev/null | grep -E '8765|5173'

echo
echo "=== test local dans le conteneur ==="
/root/go2env311/bin/python - <<'PYEOF'
import urllib.request
for url in ("http://127.0.0.1:8765/api/status", "http://127.0.0.1:5173/"):
    try:
        rep = urllib.request.urlopen(url, timeout=6)
        print(f"  {url} -> HTTP {rep.status}")
    except Exception as exc:
        print(f"  {url} -> ECHEC {exc}")
PYEOF