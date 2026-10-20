#!/bin/bash
# Installe la nouvelle interface et verifie qu'elle est bien servie.
set -u

cd /root/go2/frontend || { echo "repertoire frontend introuvable"; exit 1; }

rm -rf dist.ancien
mv dist dist.ancien
tar -xzf /root/dist.tgz || { echo "extraction impossible"; exit 1; }

echo "=== fichiers servis ==="
ls -l dist/assets/ | tail -4

BUNDLE=$(ls dist/assets | grep -E '^index-.*\.js$' | head -1)
echo "bundle attendu : $BUNDLE"

echo "=== controle HTTP ==="
/root/go2env311/bin/python - "$BUNDLE" <<'PY'
import sys
import urllib.request

bundle = sys.argv[1]
with urllib.request.urlopen("http://127.0.0.1:5173", timeout=10) as reponse:
    page = reponse.read().decode()
    print("HTTP", reponse.status)
    print("nouveau bundle present :", bundle in page)
PY
