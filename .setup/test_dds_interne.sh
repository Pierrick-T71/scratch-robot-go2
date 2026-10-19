#!/bin/bash
# DDS vers l'ordinateur de bord, a travers le robot.
#
# Apres l'ajout de la route, 192.168.123.161 repond au ping. On annonce
# maintenant notre presence en DDS directement a cette adresse.
#
# Le robot ne peut pas nous joindre en multidiffusion ; on force donc la
# decouverte en UNICAST, qui est de toute facon le mode utilise pour les
# donnees une fois les participants connus.

PY=/root/go2env311/bin/python
SONDE=/root/sonde_dds.py
CIBLE=192.168.123.161

echo "=== 1. cible joignable ==="
ping -c 2 -W 2 "$CIBLE" | tail -2

echo
echo "=== 2. ports ouverts sur l'ordinateur de bord ==="
if command -v nmap >/dev/null; then
    nmap -Pn -T4 --min-rate 800 -p 22,80,8000,8080,9991,7400-7410 "$CIBLE" 2>/dev/null \
        | grep -E "^[0-9]+/tcp|Host is"
fi

echo
echo "=== 3. banniere SSH (compte unitree/123 connu sur Go2) ==="
timeout 5 bash -c "exec 3<>/dev/tcp/$CIBLE/22; head -c 80 <&3" 2>/dev/null | tr -d '\0'
echo

echo
echo "=== 4. DDS : domaine 0, pair unicast $CIBLE ==="
timeout 50 "$PY" "$SONDE" 0 "$CIBLE" eth0 15 2>&1 | grep -vE "^\[" | head -16

echo
echo "=== 5. si rien : autres domaines ==="
for d in 1 2; do
    echo "  --- domaine $d ---"
    timeout 30 "$PY" "$SONDE" "$d" "$CIBLE" eth0 10 2>&1 | grep -E "RESULTAT|PREMIER" | head -3
done
