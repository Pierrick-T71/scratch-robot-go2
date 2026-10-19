#!/bin/bash
# Prerequis systeme. Ne modifie que les paquets, rien d'autre.
set -e
export DEBIAN_FRONTEND=noninteractive

echo "=== mise a jour des index ==="
apt-get update -qq

echo "=== installation ==="
apt-get install -y -qq --no-install-recommends \
    git \
    ca-certificates \
    build-essential \
    python3-dev \
    python3-venv \
    python3-pip \
    libyaml-cpp-dev \
    pkg-config

echo
echo "=== verification ==="
for c in git gcc g++ make; do
  command -v $c >/dev/null && echo "$c: present" || echo "$c: ABSENT"
done
python3 -m venv --help >/dev/null 2>&1 && echo "venv: disponible" || echo "venv: INDISPONIBLE"

echo
echo "=== PREREQUIS TERMINES ==="