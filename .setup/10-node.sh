#!/bin/bash
# Node.js + transfert de l'interface.
set -e
export DEBIAN_FRONTEND=noninteractive

echo "=== Node.js ==="
apt-get install -y -qq --no-install-recommends nodejs npm
node --version
npm --version

echo
echo "=== attente de l'interface ==="
mkdir -p /root/go2/frontend
if [ -f /root/go2/frontend/package.json ]; then
    echo "  deja transferee"
else
    echo "  en attente de la copie depuis Windows"
    exit 1
fi

cd /root/go2/frontend
ls -1 | head