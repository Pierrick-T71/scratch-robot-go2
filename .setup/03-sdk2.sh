#!/bin/bash
# SDK Unitree, avec reutilisation du cyclonedds deja present.
#
# POURQUOI --no-build-isolation :
#   pip cree par defaut un environnement temporaire isole pour compiler le
#   SDK. Cet environnement ne voit pas `cyclonedds`, et la compilation echoue
#   sur « Could not locate cyclonedds ». Reutiliser le venv evite cela.
set -e

VENV=/root/go2env
PY="$VENV/bin/python"

echo "=== emplacement de cyclonedds ==="
SITE=$("$PY" -c "import site; print(site.getsitepackages()[0])")
echo "site-packages : $SITE"
export CYCLONEDDS_HOME="$SITE"
export CMAKE_PREFIX_PATH="$SITE"

echo
echo "=== installation du SDK ==="
if "$PY" -m pip install --no-build-isolation --quiet \
        git+https://github.com/unitreerobotics/unitree_sdk2_python.git; then
    echo "SDK: installe"
else
    echo "SDK: ECHEC"
    echo
    echo "--- sortie detaillee ---"
    "$PY" -m pip install --no-build-isolation \
        git+https://github.com/unitreerobotics/unitree_sdk2_python.git 2>&1 | tail -40
    exit 3
fi

echo
echo "=== VERIFICATION DES IMPORTS ==="
"$PY" - <<'PYEOF'
import traceback
for m in ["unitree_sdk2py", "unitree_sdk2py.core.channel", "cyclonedds"]:
    try:
        __import__(m)
        print(f"  {m} : OK")
    except Exception:
        print(f"  {m} : ECHEC")
        traceback.print_exc()
PYEOF

echo
echo "=== LOCALISATION DES METHODES ATTENDUES ==="
"$PY" - <<'PYEOF'
import inspect
try:
    from unitree_sdk2py.g1.g1 import G1SportClient
    methodes = [m for m in dir(G1SportClient) if not m.startswith("_")]
    interest = [m for m in methodes if any(k in m.lower() for k in
                ("move", "stand", "sit", "balance", "damp", "recovery"))]
    print("  methodes de pilotage trouvees :")
    for m in sorted(interest):
        print(f"    - {m}")
except Exception as exc:
    print(f"  lecture du client impossible : {exc}")
PYEOF

echo
echo "=== SDK TERMINE ==="