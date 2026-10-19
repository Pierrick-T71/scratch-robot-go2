#!/bin/bash
# Installation du service GO2 dans le venv Python 3.11.
set -e

export PATH="/root/go2env/bin:$PATH"
VENV=/root/go2env311
PY="$VENV/bin/python"

echo "=== nettoyage des .pyc venus de Windows ==="
find /root/go2 -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find /root/go2 -name '*.pyc' -delete 2>/dev/null || true
rm -rf /root/go2/robot-service/src/go2_service.egg-info
echo "  fait"

echo
echo "=== compilation du service (syntaxe) ==="
"$PY" -m compileall -q /root/go2/robot-service/src && echo "  syntaxe : OK"

echo
echo "=== installation du service ==="
cd /root/go2/robot-service
uv pip install --python "$PY" --quiet -e ".[dev]" 2>&1 | tail -6
echo "  installe"

echo
echo "=== TESTS DU SERVICE ==="
cd /root/go2/robot-service
"$PY" -m pytest tests -q 2>&1 | tail -6

echo
echo "=== verification des imports ==="
"$PY" - <<'PYEOF'
mods = ["go2_service", "go2_service.main", "go2_service.program",
        "go2_service.interpreter", "go2_service.adapters.unitree",
        "cyclonedds", "unitree_sdk2py"]
for m in mods:
    try:
        __import__(m)
        print(f"  {m} : OK")
    except Exception as exc:
        print(f"  {m} : ECHEC -> {type(exc).__name__}: {exc}")
PYEOF

echo
echo "=== lecture des limites partagees ==="
"$PY" -c "import json;d=json.load(open('/root/go2/shared/safety-limits.json'));print('  version',d['version'],'| vmax',d['motion']['maxLinearSpeed'],'m/s')"