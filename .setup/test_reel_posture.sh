#!/bin/bash
# Test sur le robot REEL : s'asseoir en fin de programme, et vérifier
# qu'aucune consigne de mouvement ne suit (donc pas de redressement).
set -u

IP=${1:-172.16.8.11}
API=http://127.0.0.1:8765

echo "=== 1. branchement du robot (test posture = le robot s'assoit) ==="
/root/go2env311/bin/python - "$IP" "$API" <<'PY'
import json
import sys
import urllib.request

ip, api = sys.argv[1], sys.argv[2]


def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


code, body = post(
    f"{api}/api/robot/connect",
    {"robot_ip": ip, "network_interface": "eth0", "lancer_test": True},
)
print("connexion :", code, json.dumps(body, ensure_ascii=False)[:400])

code, body = post(
    f"{api}/api/mode", {"mode": "real", "adult_authorised": True}
)
print("mode :", code, json.dumps(body, ensure_ascii=False)[:200])

code, body = post(
    f"{api}/api/execution/start",
    {
        "program": {"statements": [{"kind": "posture", "posture": "sit"}]},
        "adult_authorised": True,
    },
)
print("programme assis :", code, json.dumps(body, ensure_ascii=False)[:200])
PY

sleep 6

echo
echo "=== 2. commandes reellement envoyees au robot ==="
grep -E "Commande envoyee|Rel[eé]vement|posture" /root/go2/service.log | tail -20

echo
echo "=== 3. etat du service ==="
/root/go2env311/bin/python - <<'PY'
import json
import urllib.request

status = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=5))
print("mode :", status["mode"], "| posture :", status["posture"], "| executing :", status["executing"])
PY
