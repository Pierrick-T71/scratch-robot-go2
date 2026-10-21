#!/bin/bash
# Verification : la cle est-elle presente, et le robot se branche-t-il ?
set -u

bash /usr/local/bin/demarrer.sh > /root/demarrage.log 2>&1
tail -6 /root/demarrage.log
echo

echo "=== la cle est-elle dans l'environnement du service ? ==="
for pid in $(pgrep -f 'python -m go2_service'); do
  echo -n "pid $pid : "
  tr '\0' '\n' < "/proc/$pid/environ" | grep '^GO2_ROBOT_AES_KEY' || echo "(absente de l'environnement)"
done
echo

echo "=== le service sait-il la lire dans le fichier, de toute facon ? ==="
cd /root/go2/robot-service && /root/go2env311/bin/python -c "
from go2_service.main import _robot_aes_key
print('cle trouvee par le service :', bool(_robot_aes_key()))
"
echo

echo "=== le robot se branche-t-il ? ==="
/root/go2env311/bin/python - <<'PY'
import json
import urllib.error
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8765/api/robot/connect",
    data=json.dumps(
        {
            "robot_ip": "172.16.8.11",
            "network_interface": "eth0",
            "lancer_test": True,
        }
    ).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        print(r.status, r.read().decode()[:400])
except urllib.error.HTTPError as exc:
    print(exc.code, exc.read().decode()[:400])
PY
