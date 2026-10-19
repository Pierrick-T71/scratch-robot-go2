#!/bin/bash
# Le service DDS ecoute-t-il vraiment ?
#
# On interroge les ports DDS en UDP (le DDS est en UDP, pas en TCP — d'ou
# l'absence de resultat dans les scans precedents).
#
#   - port ouvert   : quelqu'un ecoute, mais on ne se comprend pas
#   - port ferme    : personne n'ecoute -> le DDS ne tourne pas de ce cote
#   - filtre        : un pare-feu bloque -> le message est clair aussi

set -u

echo "=============================================================="
echo "  Ports UDP DDS"
echo "=============================================================="

for cible in 172.16.8.11 192.168.123.161; do
    echo
    echo "=== $cible : ports 7400-7412 en UDP ==="
    if command -v nmap >/dev/null; then
        timeout 90 nmap -sU -Pn -p 7400,7401,7410,7411,7412 "$cible" 2>/dev/null \
            | grep -E "^[0-9]+/udp|Host is"
    fi
done

echo
echo "=== capture pendant une tentative de dialogue DDS ==="
# On lance la sonde en tache de fond et on regarde ce qui part et ce qui
# revient. Un aller sans retour signifie que la porte est fermee en face.
timeout 20 tcpdump -i eth0 -nn "host 192.168.123.161 or host 172.16.8.11" \
    > /root/go2/cap_dds.txt 2>/dev/null &
TCPDUMP_PID=$!

sleep 1
timeout 14 /root/go2env311/bin/python /root/sonde_dds.py 0 192.168.123.161 eth0 10 \
    > /root/go2/sonde_dds.log 2>&1
wait $TCPDUMP_PID 2>/dev/null

echo "  --- paquets sortants (nous -> robot) ---"
grep -c "172.16.13.41 >" /root/go2/cap_dds.txt || true
grep "172.16.13.41 >" /root/go2/cap_dds.txt | head -6 | sed 's/^/    /'

echo "  --- paquets entrants (robot -> nous) ---"
grep -c "> 172.16.13.41" /root/go2/cap_dds.txt || true
grep "> 172.16.13.41" /root/go2/cap_dds.txt | head -8 | sed 's/^/    /'

echo "  --- resultat de la sonde ---"
grep -E "RESULTAT|PREMIER" /root/go2/sonde_dds.log | head -4 | sed 's/^/    /'

echo
echo "=============================================================="
