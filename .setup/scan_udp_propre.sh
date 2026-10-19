#!/bin/bash
# Quels ports DDS sont REELLEMENT ouverts ?
#
# Le test precedent etait fausse par deux choses :
#   1. un socket UDP non connecte ne recoit pas les ICMP ;
#   2. le noyau limite le debit des ICMP qu'il emet, donc certains ports
#      fermes paraissent silencieux.
#
# Ici : envoi LENT (un paquet toutes les 0,2 s), et capture des ICMP par
# tcpdump. Un port dont l'ICMP apparait est ferme. Un port absent de la
# liste est ouvert.

set -u
CIBLES="172.16.8.11 192.168.123.161"
DEBUT=7400
FIN=7424

for cible in $CIBLES; do
    echo "=============================================================="
    echo "  $cible : ports $DEBUT-$FIN"
    echo "=============================================================="

    rm -f /root/go2/icmp.txt
    tcpdump -i eth0 -nn -l "icmp and host $cible" > /root/go2/icmp.txt 2>/dev/null &
    TPID=$!
    sleep 1

    for port in $(seq $DEBUT $FIN); do
        /root/go2env311/bin/python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(0.35)
try:
    s.connect(('$cible', $port))
    s.send(b'\x00' * 24)
    try:
        s.recv(1024)
    except Exception:
        pass
except Exception:
    pass
finally:
    s.close()
" 2>/dev/null
        sleep 0.2
    done

    sleep 2
    kill $TPID 2>/dev/null
    wait $TPID 2>/dev/null

    echo "  ICMP « port unreachable » recus :"
    if [ -s /root/go2/icmp.txt ]; then
        grep -oE "udp port [0-9]+ unreachable" /root/go2/icmp.txt \
            | grep -oE "[0-9]+" | sort -n | uniq | tr '\n' ' ' | sed 's/^/    /'
        echo
    else
        echo "    aucun"
    fi

    echo "  => les ports NON listes ci-dessus sont OUVERTS (ou filtres)"
    echo
done
