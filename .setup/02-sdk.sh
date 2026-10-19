#!/bin/bash
# Environnement virtuel + SDK Unitree.
# Tout reste dans /root/go2env : rien n'est installe au systeme.
set -e

VENV=/root/go2env

echo "=== creation du venv ==="
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip --version

echo
echo "=== PYTHON UTILISE ==="
"$VENV/bin/python" --version

echo
echo "=== cyclonedds (compilation) ==="
# Cette bibliotheque n'existe pas en roue precompilee pour Python 3.13 :
# elle se compile a partir des sources, d'ou la presence de build-essential.
if "$VENV/bin/python" -m pip install --quiet cyclonedds; then
    echo "cyclonedds: installe"
else
    echo "cyclonedds: ECHEC sur Python 3.13"
    echo "-> le SDK Unitree peut exiger une version de Python plus ancienne"
    echo "->.installer python3.11 depuis les depots Debian"
    exit 2
fi

echo
echo "=== SDK unitree_sdk2_python ==="
"$VENV/bin/python" -m pip install --quiet \
    git+https://github.com/unitreerobotics/unitree_sdk2_python.git \
    && echo "SDK: installe" \
    || { echo "SDK: ECHEC"; exit 3; }

echo
echo "=== VERIFICATION DES IMPORTS ==="
"$VENV/bin/python" - <<'PYEOF'
mods = [
    "unitree_sdk2py",
    "unitree_sdk2py.core.channel",
    "cyclonedds",
]
for m in mods:
    try:
        __import__(m)
        print(f"  {m} : OK")
    except Exception as exc:
        print(f"  {m} : ECHEC -> {type(exc).__name__}: {exc}")
PYEOF

echo
echo "=== SDK TERMINE ==="