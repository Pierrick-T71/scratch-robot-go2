#!/bin/bash
# Laisse le robot libre : la liaison WebRTC est EXCLUSIVE, un canal ouvert
# empeche l'application mobile (et l'interface) de se brancher.
set -u
/root/go2env311/bin/python - <<'PY'
import json
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8765/api/robot/disconnect",
    data=b"{}",
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("deconnexion :", r.status, r.read().decode()[:200])
except Exception as exc:
    print("deconnexion :", exc)
PY
