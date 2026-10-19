#!/bin/bash
# Deploiement du service sur le conteneur + configuration de la cle AES.
set -u
APPS=/root/go2

# ---------------------------------------------------------------- 1. code
cd "$APPS/robot-service" || { echo "repertoire du service introuvable"; exit 1; }
tar -xzf /root/robot-src.tgz || { echo "extraction impossible"; exit 1; }
echo "=== code extrait ==="
ls -l src/go2_service/adapters/webrtc.py || exit 1

# ------------------------------------------------------ 2. cle AES locale
cat > "$APPS/robot.env" <<'EOF'
GO2_ROBOT_AES_KEY=4f75397f771b0df6c9d9311736557ec1
EOF
chmod 600 "$APPS/robot.env"
echo "=== cle AES ecrite dans $APPS/robot.env (droits 600) ==="

# ------------------------------------- 3. le script de demarrage la charge
if grep -q 'robot.env' /usr/local/bin/demarrer.sh; then
    echo "=== demarrer.sh lit deja robot.env ==="
else
    python3 - <<'PY'
from pathlib import Path

chemin = Path('/usr/local/bin/demarrer.sh')
texte = chemin.read_text()
ancre = 'LOG_FRONTEND="$APPS/frontend.log"\n'
ajout = ancre + '''
# Secrets locaux (cle AES du robot), hors depot.
if [ -f "$APPS/robot.env" ]; then
    set -a
    . "$APPS/robot.env"
    set +a
fi
'''
if ancre not in texte:
    raise SystemExit('ancre introuvable dans demarrer.sh')
chemin.write_text(texte.replace(ancre, ajout, 1))
print('=== demarrer.sh modifie ===')
PY
fi

# ------------------------------------------------------------- 4. controle
echo "=== controle de syntaxe ==="
"$APPS/../go2env311/bin/python" -m py_compile \
    "$APPS/robot-service/src/go2_service/adapters/webrtc.py" \
    "$APPS/robot-service/src/go2_service/main.py" \
    && echo "syntaxe OK"
