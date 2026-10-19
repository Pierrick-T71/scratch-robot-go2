#!/bin/bash
# cyclonedds 0.10.2 cherche sa bibliotheque native dans
#   $CYCLONEDDS_HOME/lib  et  $CYCLONEDDS_HOME/include
# Debian 13 installe la bibliotheque dans une arborescence "multiarch" :
#   /usr/lib/x86_64-linux-gnu/libddsc.so
# et les en-tetes dans /usr/include/dds/.
#
# On construit donc une arborescence conforme, sans rien deplacer : uniquement
# des liens symboliques vers les fichiers deja installes par apt.
set -e

VENV=/root/go2env
PY="$VENV/bin/python"
SHIM=/opt/cyclonedds

MULTIARCH=$("$PY" -c "import sysconfig; print(sysconfig.get_config_var('MULTIARCH'))")
LIBDIR="/usr/lib/$MULTIARCH"

echo "=== bibliotheque source ==="
ls -l "$LIBDIR/libddsc.so"
echo "=== en-tetes source ==="
ls -l /usr/include/dds/dds.h

echo
echo "=== arborescence conforme : $SHIM ==="
mkdir -p "$SHIM/lib" "$SHIM/include"

# Toutes les bibliotheques du binding, pas seulement ddsc.
for f in "$LIBDIR"/libddsc.so* "$LIBDIR"/libddscidl.so*; do
    [ -e "$f" ] && ln -sf "$f" "$SHIM/lib/$(basename "$f")"
done

# Les en-tetes : CycloneDDS les veut a plat sous include/dds.
ln -sfn /usr/include/dds "$SHIM/include/dds"
ln -sfn /usr/include/ddsc "$SHIM/include/ddsc"

echo "contenu de $SHIM/lib :"
ls -l "$SHIM/lib" | head -8
echo "dds.h resolu :"
ls -l "$SHIM/include/dds/dds.h"

echo
export CYCLONEDDS_HOME="$SHIM"
export CMAKE_PREFIX_PATH="$SHIM"
echo "=== compilation du binding 0.10.2 ==="
"$PY" -m pip install --quiet --no-build-isolation --no-cache-dir "cyclonedds==0.10.2" 2>&1 | tail -20
"$PY" -c "import cyclonedds; print('cyclonedds 0.10.2 : OK')"

echo
echo "=== SDK Unitree ==="
export CYCLONEDDS_HOME="$SHIM"
"$PY" -m pip install --quiet --no-build-isolation --no-cache-dir \
    git+https://github.com/unitreerobotics/unitree_sdk2_python.git 2>&1 | tail -20
"$PY" -c "import unitree_sdk2py; print('SDK : OK')"

echo
echo "=== BILAN ==="
"$PY" -m pip list 2>/dev/null | grep -Ei 'cyclonedds|unitree'