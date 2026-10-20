#!/bin/bash
# Controle rapide du service depose.
set -u
/root/go2env311/bin/python - <<'PY'
import json
import urllib.request

status = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=5))
print("etat :", json.dumps(status, ensure_ascii=False))
print("champs posture presents :", "posture" in status)
PY
