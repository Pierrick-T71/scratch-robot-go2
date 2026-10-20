#!/bin/bash
# Programme « s'asseoir » sur le robot REEL deja branche, et lecture du
# journal des commandes envoyees.
set -u
API=http://127.0.0.1:8765

/root/go2env311/bin/python - <<'PY'
import json
import urllib.error
import urllib.request

API = "http://127.0.0.1:8765"


def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


print("mode :", post(f"{API}/api/mode", {"mode": "real", "adult_authorised": True})[0])
print(
    "programme assis :",
    post(
        f"{API}/api/execution/start",
        {
            "program": {"statements": [{"kind": "posture", "posture": "sit"}]},
            "adult_authorised": True,
        },
    ),
)
PY

sleep 8

echo
echo "=== commandes envoyees au robot ==="
grep -E "Commande envoyee|Rel[eé]vement" /root/go2/service.log | tail -20

echo
echo "=== retour en simulation ==="
/root/go2env311/bin/python - <<'PY'
import json
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8765/api/mode",
    data=json.dumps({"mode": "simulation", "adult_authorised": True}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    print("mode :", json.loads(r.read().decode())["mode"])
PY
