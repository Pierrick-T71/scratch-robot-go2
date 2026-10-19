#!/bin/bash
# ARBORESCENCE ATTENDUE PAR cyclonedds 0.10.2
#
# `good_directory()` dans buildhelp/cyclone_search.py teste TROIS choses :
#   <dir>/include existe    -> /usr/include          (symlink)
#   <dir>/bin    existe    -> !! le test est `exists()`, pas « contient des
#                              binaires ». Debian n'installe rien dans un
#                              prefixe /usr/local/cyclonedds/bin, et c'est
#                              justement ce qui faisait echouer la detection.
#   <dir>/lib/libddsc.so   -> /usr/lib/<multiarch>  (symlink)
set -e

VENV=/root/go2env
PY="$VENV/bin/python"
SHIM=/opt/cyclonedds

MULTIARCH=$("$PY" -c "import sysconfig; print(sysconfig.get_config_var('MULTIARCH'))")
LIBDIR="/usr/lib/$MULTIARCH"

echo "=== construction de $SHIM ==="
rm -rf "$SHIM"
mkdir -p "$SHIM/lib" "$SHIM/include" "$SHIM/bin"

# Les trois conditions de good_directory().
ln -sfn /usr/include/dds "$SHIM/include/dds"
ln -sfn /usr/include/ddsc "$SHIM/include/ddsc"
for f in "$LIBDIR"/libddsc.so*; do
    [ -e "$f" ] && ln -sf "$f" "$SHIM/lib/$(basename "$f")"
done
# `bin/` doit simplement EXISTER. On y met les outils DDS de Debian.
for tool in /usr/bin/ddsperf /usr/bin/idl2c ddsconfig; do
    [ -e "$tool" ] && ln -sf "$tool" "$SHIM/bin/$(basename "$tool")"
done
true

echo "verification des trois conditions :"
[ -d "$SHIM/include" ] && echo "  include : OK" || echo "  include : MANQUANT"
[ -d "$SHIM/bin" ]    && echo "  bin     : OK" || echo "  bin     : MANQUANT"
[ -f "$SHIM/lib/libddsc.so" ] && echo "  lib/libddsc.so : OK" || echo "  lib/libddsc.so : MANQUANT"

export CYCLONEDDS_HOME="$SHIM"

echo
echo "=== cyclonedds 0.10.2 ==="
"$PY" -m pip install --no-cache-dir --no-build-isolation "cyclonedds==0.10.2" 2>&1 | tail -8
"$PY" -c "import cyclonedds; print('  import cyclonedds : OK')"

echo
echo "=== SDK Unitree ==="
"$PY" -m pip install --no-cache-dir --no-build-isolation \
    git+https://github.com/unitreerobotics/unitree_sdk2_python.git 2>&1 | tail -8
"$PY" -c "import unitree_sdk2py; print('  import unitree_sdk2py : OK')"

echo
echo "=== BILAN ==="
"$PY" -m pip list 2>/dev/null | grep -Ei 'cyclonedds|unitree'