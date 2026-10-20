#!/bin/bash
# Depuis la position assise :
#   1. "tourner a gauche de 90 degres" -> le cap doit changer de 90 degres
#   2. "s'asseoir" en dernier -> le robot doit RESTER assis
set -u
IP=${1:-172.16.8.11}
API=http://127.0.0.1:8765

/root/go2env311/bin/python - "$IP" "$API" <<'PY'
import json
import math
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
time.sleep(2)
s = statut()
print("depart : posture", s.get("posture"), "hauteur", (s.get("position") or {}).get("z"),
      "cap", round(s.get("yawRad") or 0, 3))
cap_avant = s.get("yawRad") or 0.0

print()
print("=== programme : tourner a gauche de 90 degres ===")
print(post(f"{api}/api/execution/start",
           {"program": {"statements": [{"kind": "turn", "direction": "left", "degrees": 90}]},
            "adult_authorised": True})[0])
depart = time.monotonic()
while time.monotonic() - depart < 12:
    time.sleep(1)
    s = statut()
    if not s.get("executing"):
        break
s = statut()
cap_apres = s.get("yawRad") or 0.0
ecart = (cap_apres - cap_avant) % (2 * math.pi)
if ecart > math.pi:
    ecart -= 2 * math.pi
print(f"  cap avant {cap_avant:.3f}  apres {cap_apres:.3f}  ecart {math.degrees(ecart):.1f} degres")
print("  hauteur :", (s.get("position") or {}).get("z"), "posture :", s.get("posture"))

print()
print("=== programme : s'asseoir (en dernier) ===")
print(post(f"{api}/api/execution/start",
           {"program": {"statements": [{"kind": "posture", "posture": "sit"}]},
            "adult_authorised": True})[0])
depart = time.monotonic()
for i in range(10):
    time.sleep(1)
    s = statut()
    print(f"  t+{time.monotonic() - depart:4.1f}s  hauteur={(s.get('position') or {}).get('z')}  "
          f"posture={s.get('posture')}", flush=True)

print()
print("=== retour en simulation ===")
print(post(f"{api}/api/mode", {"mode": "simulation", "adult_authorised": True})[0])
PY
