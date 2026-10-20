#!/bin/bash
# Le robot DEJA DEBOUT avance-t-il ? (discrimine : transition de posture
# ou commande Move ignoree par le robot)
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


for essai in range(5):
    code, body = post(
        f"{api}/api/robot/connect",
        {"robot_ip": ip, "network_interface": "eth0", "lancer_test": True},
    )
    if code == 200:
        print("connexion :", code)
        break
    print(f"  essai {essai + 1} : {code}")
    time.sleep(4)
else:
    raise SystemExit("liaison impossible")

print("mode :", post(f"{api}/api/mode", {"mode": "real", "adult_authorised": True})[0])

print()
print("=== 1. programme « se mettre debout » ===")
print(post(f"{api}/api/execution/start",
           {"program": {"statements": [{"kind": "posture", "posture": "stand"}]},
            "adult_authorised": True})[0])
time.sleep(6)
s = statut()
print("  hauteur :", (s.get("position") or {}).get("z"), "posture :", s.get("posture"))

print()
print("=== 2. programme « avancer de 2 s », robot DEJA DEBOUT ===")
avant = (statut().get("position") or {})
print("  depart :", avant)
print(post(f"{api}/api/execution/start",
           {"program": {"statements": [{"kind": "move", "direction": "forward", "seconds": 2}]},
            "adult_authorised": True})[0])
depart = time.monotonic()
for i in range(16):
    s = statut()
    p = s.get("position") or {}
    print(
        f"  t+{time.monotonic() - depart:5.1f}s  x={p.get('x')}  y={p.get('y')}  "
        f"z={p.get('z')}  executing={s.get('executing')}",
        flush=True,
    )
    time.sleep(0.5)

print()
print("=== retour en simulation ===")
print(post(f"{api}/api/mode", {"mode": "simulation", "adult_authorised": True})[0])
PY
