#!/bin/bash
# Le DDS ecoute-t-il sur un port plus haut ?
#
# CycloneDDS choisit son port de decouverte unicast selon l'index du
# participant : 7410 + 2 x index. Notre premiere tentative n'a couvert que
# les index 0 a 4 (ports 7410 a 7418).
#
# On balaie donc toute la plage, LENTEMENT (1,8 s entre chaque envoi) : le
# noyau limite a environ un ICMP par seconde, et aller plus vite produirait
# des faux « ouverts ».

set -u
CIBLE=${1:-192.168.123.161}

echo "=============================================================="
echo "  Ports DDS de decouverte sur $CIBLE"
echo "=============================================================="
echo

rm -f /root/go2/icmp2.txt
tcpdump -i eth0 -nn -l "icmp and host $CIBLE" > /root/go2/icmp2.txt 2>/dev/null &
TPID=$!
sleep 1

for port in $(seq 7400 7430); do
    /root/go2env311/bin/python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(0.6)
try:
    s.connect(('$CIBLE', $port))
    s.send(b'\x00' * 24)
    try:
        s.recv(512)
    except Exception:
        pass
except Exception:
    pass
finally:
    s.close()
" 2>/dev/null
    printf "."
    sleep 1.8
done
echo

sleep 3
kill $TPID 2>/dev/null
wait $TPID 2>/dev/null

echo
echo "  ports ayant repondu « unreachable » (donc FERMES) :"
FERMES=$(grep -oE "udp port [0-9]+ unreachable" /root/go2/icmp2.txt \
    | grep -oE "[0-9]+" | sort -n | uniq)
echo "$FERMES" | tr '\n' ' ' | sed 's/^/    /'
echo
echo
echo "  ports SILENCIEUX (donc OUVERTS ou filtres) :"
for port in $(seq 7400 7430); do
    if ! echo "$FERMES" | grep -qx "$port"; then
        printf "%s " "$port"
    fi
done
echo
echo
echo "  => tout port silencieux est un candidat : c'est la que le DDS ecoute."
echo "=============================================================="
