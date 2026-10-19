#!/bin/bash
# Bibliotheque native CycloneDDS, puis cyclonedds 0.10.x, puis le SDK Unitree.
#
# CHAINAGE DES VERSIONS, explique :
#   - le SDK Unitree exige `cyclonedds==0.10.2` (ligne de son pyproject.toml)
#   - `cyclonedds` 11.x s'installe sans bibliotheque native : il embarque tout.
#     Il ne convient donc pas au SDK, qui cherche un CYCLONEDDS_HOME.
#   - le paquet Debian `cyclonedds-dev` fournit les en-tetes et la
#     bibliotheque C, ce qui permet de compiler le binding 0.10.x.
set -e

VENV=/root/go2env
PY="$VENV/bin/python"
export DEBIAN_FRONTEND=noninteractive

echo "=== bibliotheque native ==="
apt-get install -y -qq --no-install-recommends cyclonedds-dev cyclonedds-tools
dpkg -L cyclonedds-dev | grep -E 'libcyclonedds.*\.so$|\.pc$' | head -5

PREFIX=/usr
echo "CYCLONEDDS_HOME : $PREFIX"
export CYCLONEDDS_HOME="$PREFIX"
export CMAKE_PREFIX_PATH="$PREFIX"

echo
echo "=== binding python 0.10.2 (celui demande par le SDK) ==="
"$PY" -m pip uninstall -y --quiet cyclonedds >/dev/null 2>&1 || true
"$PY" -m pip install --quiet --no-build-isolation --no-cache-dir "cyclonedds==0.10.2"
"$PY" -c "import cyclonedds; print('cyclonedds 0.10.2 : installe')"

echo
echo "=== SDK Unitree ==="
"$PY" -m pip install --quiet --no-build-isolation --no-cache-dir \
    git+https://github.com/unitreerobotics/unitree_sdk2_python.git
echo "SDK : installe"

echo
echo "=== IMPORTS ==="
"$PY" - <<'PYEOF'
import traceback
for m in ["cyclonedds", "unitree_sdk2py", "unitree_sdk2py.core.channel"]:
    try:
        __import__(m)
        print(f"  {m} : OK")
    except Exception:
        print(f"  {m} : ECHEC")
        traceback.print_exc()
PYEOF

echo
echo "=== VERSION INSTALLEE ==="
"$PY" -m pip list 2>/dev/null | grep -Ei 'cyclonedds|unitree'