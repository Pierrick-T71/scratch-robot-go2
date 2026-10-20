#!/bin/bash
# Programme « avancer » lance depuis la position assise :
# la robot se releve-t-il ET avance-t-il ?
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


print("=== branchement (test posture = robot assis) ===")
for essai in range(5):
    code, body = post(
        f"{api}/api/robot/connect",
        {"robot_ip": ip, "network_interface": "eth0", "lancer_test": True},
    )
    if code == 200:
        print("connexion :", code, body[:120])
        break
    print(f"  essai {essai + 1} : {code} {body[:120]}")
    time.sleep(4)
else:
    raise SystemExit("liaison impossible : on ne mesure rien")

code, body = post(f"{api}/api/mode", {"mode": "real", "adult_authorised": True})
print("mode :", code, body[:120])
if code != 200:
    raise SystemExit("mode reel refuse : on ne mesure rien")

s = statut()
print("depart :", s.get("position"), s.get("posture"))

print()
print("=== programme « avancer de 2 s » ===")
code, body = post(
    f"{api}/api/execution/start",
    {
        "program": {"statements": [{"kind": "move", "direction": "forward", "seconds": 2}]},
        "adult_authorised": True,
    },
)
print("demande :", code, body[:120])

depart = time.monotonic()
for i in range(30):
    s = statut()
    p = s.get("position") or {}
    print(
        f"  t+{time.monotonic() - depart:5.1f}s  x={p.get('x')}  y={p.get('y')}  "
        f"z={p.get('z')}  posture={s.get('posture')}  executing={s.get('executing')}",
        flush=True,
    )
    time.sleep(0.5)

print()
print("=== retour en simulation ===")
print(post(f"{api}/api/mode", {"mode": "simulation", "adult_authorised": True})[0])
PY
