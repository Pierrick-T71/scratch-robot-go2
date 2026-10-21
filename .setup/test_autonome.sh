#!/bin/bash
# Mode autonome : le bouton envoie-t-il la bonne commande, et le robot
# s'arrete-t-il quand on le coupe ? (test court, 4 s)
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
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def etat():
    with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=10) as r:
        return json.load(r)


avant = etat()["position"]
print("avant :", avant)

print("activation :", post("http://127.0.0.1:8765/api/robot/autonome", {"enabled": True}))
for i in range(4):
    time.sleep(1)
    print("  ", etat()["position"])

print("desactivation :", post("http://127.0.0.1:8765/api/robot/autonome", {"enabled": False}))
time.sleep(2)
print("apres :", etat()["position"])
PY
