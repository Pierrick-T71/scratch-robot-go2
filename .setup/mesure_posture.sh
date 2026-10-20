#!/bin/bash
# Mesure : le robot se releve-t-il tout seul, ou apres une de NOS commandes ?
#
# La hauteur du robot (position.z) est lue dans l'etat publie par le SDK :
# on la suit pendant que le robot est assis, puis pendant qu'un programme
# se termine.
set -u
IP=${1:-172.16.8.11}
API=http://127.0.0.1:8765

/root/go2env311/bin/python - "$IP" "$API" <<'PY'
import json
import sys
import time
import urllib.error
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
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def statut():
    with urllib.request.urlopen(f"{api}/api/status", timeout=10) as r:
        return json.loads(r.read().decode())


def hauteur():
    s = statut()
    z = (s.get("position") or {}).get("z")
    return z, s.get("posture"), s.get("mode")


print("=== 1. branchement (le test de posture envoie Sit) ===")
code, body = post(
    f"{api}/api/robot/connect",
    {"robot_ip": ip, "network_interface": "eth0", "lancer_test": True},
)
print("connexion :", code, body[:200])
print("mode :", post(f"{api}/api/mode", {"mode": "real", "adult_authorised": True})[0])

print()
print("=== 2. robot assis, AUCUNE commande de notre part pendant 30 s ===")
for i in range(15):
    z, posture, mode = hauteur()
    print(f"  t+{i * 2:02d}s  hauteur={z}  posture={posture}  mode={mode}", flush=True)
    time.sleep(2)

print()
print("=== 3. programme « s'asseoir » (StandUp, Sit, puis arret) ===")
code, body = post(
    f"{api}/api/execution/start",
    {
        "program": {"statements": [{"kind": "posture", "posture": "sit"}]},
        "adult_authorised": True,
    },
)
print("demande :", code, body[:120])
for i in range(12):
    z, posture, mode = hauteur()
    print(f"  t+{i * 2:02d}s  hauteur={z}  posture={posture}", flush=True)
    time.sleep(2)

print()
print("=== retour en simulation ===")
print(post(f"{api}/api/mode", {"mode": "simulation", "adult_authorised": True})[0])
PY
