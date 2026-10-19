#!/bin/bash
# Qui vit sur le reseau interne du robot ?
#
# On a trouve 192.168.123.161 (ordinateur de bord, avec RTSP et WebRTC).
# Mais le DDS n'y ecoute pas. Le DDS tourne peut-etre sur une AUTRE carte
# du robot, avec une autre adresse.
#
# On balaie donc tout le /24 en TCP et en UDP, sans supposer que les hotes
# repondent au ping.

set -u

echo "=============================================================="
echo "  Reseau interne du robot : 192.168.123.0/24"
echo "=============================================================="

echo
echo "=== 1. hotes avec un port TCP ouvert (scan SYN, sans ping) ==="
nmap -sS -Pn -T4 --min-rate 1500 -p 22,23,80,443,8080,8551,9991,11514 \
    192.168.123.0/24 2>/dev/null \
    | grep -E "Nmap scan report|^[0-9]+/tcp" | sed 's/^/  /'

echo
echo "=== 2. qui ecoute en UDP sur les ports DDS (7400-7412) ? ==="
echo "  (envoi lent : un paquet toutes les 1,5 s, pour ne pas saturer"
echo "   la limite de debit des ICMP du noyau)"
for ip in 192.168.123.161 192.168.123.18 192.168.123.1 192.168.123.168 192.168.123.100; do
    /root/go2env311/bin/python -c "
import socket, errno, sys
ip = '$ip'
ouverts = []
for port in (7400, 7410, 7411, 7412):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.2)
    try:
        s.connect((ip, port))
        s.send(b'\x00' * 24)
        try:
            s.recv(512)
            ouverts.append(port)
        except socket.timeout:
            ouverts.append(port)
        except OSError:
            pass
    except OSError:
        pass
    finally:
        s.close()
print(f'  {ip:18s} ports ouverts : {ouverts if ouverts else \"aucun\"}')
" 2>/dev/null
    sleep 1.6
done

echo
echo "=== 3. le robot repond-il a une multidiffusion DDS ? ==="
echo "  Ecoute de 239.255.0.1:7400 pendant 10 s depuis cette machine..."
timeout 10 tcpdump -i eth0 -nn "udp dst port 7400 or udp src port 7400" 2>/dev/null \
    | head -8 | sed 's/^/  /'
echo "  (fin)"

echo
echo "=============================================================="
