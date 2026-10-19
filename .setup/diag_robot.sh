#!/bin/bash
# Le robot Go2 publie-t-il en DDS ? et que repond-il ?
#
# Point de vigilance : '172.16.8.11' est une sous-chaine de '172.16.8.112'.
# On exige donc un separateur apres l'adresse.

set -u
IP=${1:-172.16.8.11}
DUREE=${2:-15}

echo "=============================================================="
echo "  Robot $IP"
echo "=============================================================="

echo
echo "=== 1. capture de $DUREE s sur eth0 ==="
timeout "$DUREE" tcpdump -i eth0 -nn -c 2000 2>/dev/null > /root/go2/cap_robot.txt

TOTAL=$(wc -l < /root/go2/cap_robot.txt)
echo "  $TOTAL paquets capture(s) au total"

# Separateur obligatoire : 172.16.8.11 suivi d'un point ou d'un espace.
DEPUIS=$(grep -cE "(^|[^0-9])${IP}[. ]" /root/go2/cap_robot.txt || true)
echo "  paquets impliquant le robot : $DEPUIS"
if [ "$DEPUIS" -gt 0 ]; then
    echo "  --- detail ---"
    grep -E "(^|[^0-9])${IP}[. ]" /root/go2/cap_robot.txt | head -20
fi

echo
echo "=== 2. multidiffusion DDS (ports 7400-7450) ==="
DDS=$(grep -cE '\.(74[0-5][0-9])( |:)' /root/go2/cap_robot.txt || true)
echo "  $DDS paquet(s) sur les ports DDS"
if [ "$DDS" -gt 0 ]; then
    grep -E '\.(74[0-5][0-9])( |:)' /root/go2/cap_robot.txt | head -10
fi

echo
echo "=== 3. ports TCP ouverts sur le robot ==="
for p in 22 23 80 443 8080 8765 9999 11514 12000; do
    if timeout 2 bash -c "exec 3<>/dev/tcp/$IP/$p" 2>/dev/null; then
        echo "  port $p : OUVERT"
    fi
done

echo
echo "=== 4. banniere SSH ==="
timeout 5 bash -c "exec 3<>/dev/tcp/$IP/22; head -c 80 <&3" 2>/dev/null || echo "  pas de SSH"

echo
echo "=== 5. le robot repond-il a une requete HTTP ? ==="
for p in 80 8080 9999; do
    REP=$(timeout 4 bash -c "exec 3<>/dev/tcp/$IP/$p; printf 'GET / HTTP/1.0\r\n\r\n' >&3; head -c 200 <&3" 2>/dev/null || true)
    if [ -n "$REP" ]; then
        echo "  --- port $p ---"
        echo "$REP" | head -4 | sed 's/^/    /'
    fi
done

echo
echo "=============================================================="
