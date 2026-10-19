#!/bin/bash
# Ou se cache le DDS ?
#
# On sait maintenant :
#   - la route vers 192.168.123.0/24 passe par le robot et fonctionne ;
#   - 192.168.123.161 repond, mais RIEN n'ecoute sur les ports DDS ;
#   - le port 9991 (WebRTC Unitree) est ouvert sur les deux adresses.
#
# Le DDS n'est donc pas sur .161. On balaie tout le /24 interne a la
# recherche de qui que ce soit qui ecoute en DDS.

set -u

echo "=============================================================="
echo "  Balaie le reseau interne du robot"
echo "=============================================================="

echo
echo "=== 1. hotes vivants sur 192.168.123.0/24 ==="
nmap -sn -T4 --min-rate 1000 192.168.123.0/24 2>/dev/null \
    | grep -E "Nmap scan report" | sed 's/^/  /'

echo
echo "=== 2. ports DDS en UDP sur l'ensemble du /24 ==="
echo "  (le DDS est en UDP : un port ouvert ici = un participant DDS)"
for ip in 192.168.123.161 192.168.123.18 192.168.123.1 192.168.123.100; do
    REP=$(timeout 25 nmap -sU -Pn -p 7400,7410,7411,7412 "$ip" 2>/dev/null \
        | grep -E "^[0-9]+/udp")
    if [ -n "$REP" ]; then
        echo "  --- $ip ---"
        echo "$REP" | sed 's/^/    /'
    fi
done

echo
echo "=== 3. ports TCP sur 192.168.123.161 (tout) ==="
nmap -Pn -T4 --min-rate 1000 -p- 192.168.123.161 2>/dev/null \
    | grep -E "^[0-9]+/tcp|Host is" | sed 's/^/  /'

echo
echo "=== 4. le port 9991 repond-il a quelque chose ? ==="
# Certains services Unitree attendent un en-tete precis avant de repondre.
timeout 6 bash -c "exec 3<>/dev/tcp/192.168.123.161/9991; printf 'GET / HTTP/1.0\r\n\r\n' >&3; head -c 300 <&3" \
    2>/dev/null | tr -d '\0' | sed 's/^/  /'
echo

echo
echo "=== 5. capture : le robot emet-il vers nous quand on le sollicite ? ==="
timeout 12 tcpdump -i eth0 -nn "net 192.168.123.0/24" 2>/dev/null | head -12 | sed 's/^/  /'

echo
echo "=============================================================="
