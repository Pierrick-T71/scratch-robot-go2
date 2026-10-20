#!/bin/bash
# Branchement seul, pour isoler la liaison WebRTC.
set -u
IP=${1:-172.16.8.11}
for essai in 1 2 3; do
  echo "--- essai $essai ---"
  /root/go2env311/bin/python - "$IP" <<'PY'
import json
import sys
import urllib.error
import urllib.request

ip = sys.argv[1]
req = urllib.request.Request(
    "http://127.0.0.1:8765/api/robot/connect",
    data=json.dumps(
        {"robot_ip": ip, "network_interface": "eth0", "lancer_test": False}
    ).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(r.status, r.read().decode()[:300])
except urllib.error.HTTPError as exc:
    print(exc.code, exc.read().decode()[:300])
PY
  sleep 5
done
