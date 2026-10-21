#!/bin/bash
# Brancher le robot et regarder ce que publie le lidar.
set -u

/root/go2env311/bin/python - <<'PY'
import json
import urllib.error
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8765/api/robot/connect",
    data=json.dumps(
        {
            "robot_ip": "172.16.8.11",
            "network_interface": "eth0",
            "lancer_test": True,
        }
    ).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        print(r.status, r.read().decode()[:300])
except urllib.error.HTTPError as exc:
    print(exc.code, exc.read().decode()[:300])
PY

sleep 6

echo
echo "=== journal : lidar ==="
grep -a 'Lidar' /root/go2/service.log | tail -5 | cut -c1-500

echo
echo "=== les messages lidar bruts du SDK ==="
grep -a 'utlidar' /root/go2/service.log | tail -2 | cut -c1-500
