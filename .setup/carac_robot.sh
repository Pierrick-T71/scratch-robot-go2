#!/bin/bash
# Caracterisation du robot 172.16.8.11
#
# Objectif : savoir a quoi on parle. Un Go2 expose typiquement un SSH, des
# services Unitree, et publie en DDS. On regarde tout.

set -u
IP=${1:-172.16.8.11}

echo "=============================================================="
echo "  Caracterisation de $IP"
echo "=============================================================="

echo
echo "=== 1. adresse MAC (identification du constructeur) ==="
ip neigh flush "$IP" 2>/dev/null || true
ping -c 1 -W 2 "$IP" >/dev/null 2>&1 || true
ip neigh show "$IP" 2>/dev/null

echo
echo "=== 2. ports TCP ouverts (scan complet) ==="
if command -v nmap >/dev/null; then
    nmap -Pn -T4 --min-rate 1200 -p- "$IP" 2>/dev/null | grep -E '^[0-9]+/tcp|Host is'
else
    echo "  nmap absent"
fi

echo
echo "=== 3. banniere SSH ==="
timeout 5 bash -c "exec 3<>/dev/tcp/$IP/22; head -c 120 <&3" 2>/dev/null \
    | tr -d '\0' || echo "  (rien sur le port 22)"

echo
echo
echo "=== 4. services Unitree connus ==="
# Les services Unitree ecoutent souvent sur ces ports.
for p in 5000 8080 9999 11514 12000 43893; do
    if timeout 2 bash -c "exec 3<>/dev/tcp/$IP/$p" 2>/dev/null; then
        echo "  port $p : OUVERT"
    fi
done

echo
echo "=== 5. capture : le robot emet-il spontanement ? (20 s) ==="
timeout 20 tcpdump -i eth0 -nn -c 3000 2>/dev/null > /root/go2/cap2.txt
TOTAL=$(wc -l < /root/go2/cap2.txt)
echo "  $TOTAL paquets captures sur eth0"
# Separateur obligatoire : 172.16.8.11 suivi d'un point ou d'un espace.
N=$(grep -cE "(^|[^0-9])${IP}[. ]" /root/go2/cap2.txt || true)
echo "  dont impliquant le robot : $N"
if [ "$N" -gt 0 ]; then
    grep -E "(^|[^0-9])${IP}[. ]" /root/go2/cap2.txt | head -15 | sed 's/^/    /'
fi

echo
echo "=== 6. multidiffusion recue (toutes sources) ==="
echo "  groupes vus pendant la capture :"
grep -oE '> (2[2-3][0-9])\.[0-9]+\.[0-9]+\.[0-9]+\.' /root/go2/cap2.txt 2>/dev/null \
    | sort | uniq -c | sort -rn | head -10 | sed 's/^/    /'
echo "  ports DDS 7400-7450 vus :"
grep -cE '\.(74[0-5][0-9])[ :]' /root/go2/cap2.txt || echo "    0"

echo
echo "=============================================================="
