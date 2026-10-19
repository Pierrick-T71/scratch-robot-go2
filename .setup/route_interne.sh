#!/bin/bash
# Le DDS du Go2 vit sur le reseau INTERNE du robot, pas sur son adresse
# externe.
#
# Le robot (172.16.8.11) route vers un sous-reseau 192.168.123.0/24 ou
# resident son ordinateur de bord. Tant qu'on n'a pas de route vers ce
# sous-reseau, les paquets DDS unicast n'ont nulle part ou aller — et la
# multidiffusion, elle, ne franchit de toute facon pas.
#
# Ce script ajoute la route et verifie ce qu'on atteint.

set -u
EXTERNE=${1:-172.16.8.11}
INTERNE="192.168.123.0/24"

echo "=============================================================="
echo "  Ouverture de la route vers le reseau interne du robot"
echo "=============================================================="

echo
echo "=== 1. route deja presente ? ==="
ip route show | grep -F "192.168.123" || echo "  aucune route vers 192.168.123.0/24"

echo
echo "=== 2. ajout de la route ==="
if ip route show | grep -qF "192.168.123.0/24"; then
    echo "  deja en place"
else
    ip route add "$INTERNE" via "$EXTERNE" 2>&1 && echo "  route ajoutee via $EXTERNE"
fi
ip route show | grep -F "192.168.123" | sed 's/^/  /'

echo
echo "=== 3. le reseau interne repond-il ? ==="
for ip in 192.168.123.161 192.168.123.18 192.168.123.1 192.168.123.99; do
    if timeout 3 ping -c 1 -W 2 "$ip" >/dev/null 2>&1; then
        echo "  $ip : REPOND"
    else
        echo "  $ip : silencieux"
    fi
done

echo
echo "=== 4. balayage du /24 interne (les hotes presents) ==="
if command -v nmap >/dev/null; then
    nmap -sn -T4 --min-rate 800 192.168.123.0/24 2>/dev/null | grep -E "Nmap scan report" | sed 's/^/  /'
else
    echo "  nmap absent"
fi

echo
echo "=============================================================="
