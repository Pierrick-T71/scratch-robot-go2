#!/bin/bash
# Scenario complet : brancher, se lever, la carte du lidar arrive-t-elle ?
set -u

/root/go2env311/bin/python - <<'PY'
import json
import time
import urllib.request


def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.status, r.read().decode()[:200]


print("connexion :", post(
    "http://127.0.0.1:8765/api/robot/connect",
    {"robot_ip": "172.16.8.11", "network_interface": "eth0", "lancer_test": False},
)[0])
time.sleep(3)
print("se mettre debout :", post(
    "http://127.0.0.1:8765/api/execution/start",
    {
        "program": {"statements": [{"kind": "posture", "posture": "stand"}]},
        "adult_authorised": True,
    },
)[0])
time.sleep(10)

reponse = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/robot/lidar", timeout=10))
points = reponse.get("points") or []
print("lidar actif :", reponse.get("actif"), "| cases :", len(points))
if points:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    print(f"  x : {min(xs):.1f} .. {max(xs):.1f}   y : {min(ys):.1f} .. {max(ys):.1f}")
PY
