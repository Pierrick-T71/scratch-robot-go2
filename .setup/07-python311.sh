#!/bin/bash
# Contournement du blocage Python 3.13.
#
# Le binding cyclonedds (0.10.2 comme 0.10.5) appelle `_Py_IsFinalizing`,
# une API PRIVEE de CPython SUPPRIMEE en Python 3.13. Aucune version de
# cyclonedds <= 0.10.5 ne compile donc en 3.13, et Debian 13 ne fournit
# ni python3.11 ni python3.12.
#
# Solution : `uv`, qui installe des interpreteurs CPython precompiles
# independamment des depots de la distribution. Aucune compilation depuis les
# sources, donc rapide.
set -e

VENV=/root/go2env311

echo "=== installation de uv ==="
/root/go2env/bin/python -m pip install --quiet uv
export PATH="/root/go2env/bin:$PATH"
uv --version

echo
echo "=== CPython 3.11 (precompile) ==="
uv python install 3.11 2>&1 | tail -3
uv python list 2>&1 | grep -i '3\.11' | head -3

echo
echo "=== creation du venv 3.11 ==="
rm -rf "$VENV"
uv venv --python 3.11 "$VENV"
"$VENV/bin/python" --version

echo
echo "=== pip dans ce venv ==="
"$VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
uv pip install --python "$VENV/bin/python" --quiet --upgrade pip setuptools wheel

echo
echo "=== cyclonedds 0.10.2 sur 3.11 ==="
export CYCLONEDDS_HOME=/opt/cyclonedds
uv pip install --python "$VENV/bin/python" --no-build-isolation "cyclonedds==0.10.2" 2>&1 | tail -5
"$VENV/bin/python" -c "import cyclonedds; print('  cyclonedds : OK')"

echo
echo "=== SDK Unitree sur 3.11 ==="
uv pip install --python "$VENV/bin/python" --no-build-isolation \
    git+https://github.com/unitreerobotics/unitree_sdk2_python.git 2>&1 | tail -5
"$VENV/bin/python" -c "import unitree_sdk2py; print('  unitree_sdk2py : OK')"

echo
echo "=== BILAN ==="
uv pip list --python "$VENV/bin/python" 2>/dev/null | grep -Ei 'cyclonedds|unitree'