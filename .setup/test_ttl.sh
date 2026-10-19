#!/bin/bash
# Le robot cache-t-il un second ordinateur derriere lui ?
#
# 172.16.8.11 et 192.168.123.161 exposent exactement les memes ports
# (8551 et 9991). Deux hypotheses :
#
#   A. c'est la MEME machine (deux interfaces) ;
#   B. .161 est une machine DERRIERE un routeur, et ce routeur ne laisse
#      passer que certains ports — auquel cas le DDS pourrait tourner
#      derriere sans qu'on le voie.
#
# Le TTL tranche : chaque routeur traversé decremente le TTL.
# Meme TTL = meme machine. TTL plus bas = machine derriere un routeur.

set -u

echo "=============================================================="
echo "  TTL : meme machine ou machine derriere ?"
echo "=============================================================="
echo
echo "=== 1. TTL vers l'adresse Wi-Fi du robot ==="
ping -c 2 -W 2 172.16.8.11 | grep -E "ttl=|rtt" | sed 's/^/  /'
echo
echo "=== 2. TTL vers l'ordinateur interne ==="
ping -c 2 -W 2 192.168.123.161 | grep -E "ttl=|rtt" | sed 's/^/  /'
echo
echo "  lecture : un TTL plus BAS de 1 indique un routeur traverse."
echo

echo "=== 3. chemin vers l'ordinateur interne ==="
if command -v traceroute >/dev/null; then
    traceroute -n -m 4 -w 2 192.168.123.161 2>/dev/null | sed 's/^/  /'
else
    echo "  traceroute absent, lecture du TTL ci-dessus suffit"
fi
echo

echo "=== 4. meme test sur le port 8551 (RTSP) ==="
# Un service identique sur les deux adresses suggere fortement la meme
# machine. On compare les en-tetes date/heure de la reponse RTSP : deux
# machines distinctes ont presque toujours des horloges legerement
# differentes.
for cible in 172.16.8.11 192.168.123.161; do
    DATE_REP=$(timeout 5 bash -c "
        exec 3<>/dev/tcp/$cible/8551
        printf 'OPTIONS rtsp://$cible RTSP/1.0\r\nCSeq: 1\r\n\r\n' >&3
        head -c 300 <&3" 2>/dev/null | grep -i "^Date:" | tr -d '\r')
    echo "  $cible : $DATE_REP"
done

echo
echo "=== 5. identification du serveur RTSP ==="
for cible in 172.16.8.11 192.168.123.161; do
    SERVEUR=$(timeout 5 bash -c "
        exec 3<>/dev/tcp/$cible/8551
        printf 'OPTIONS rtsp://$cible RTSP/1.0\r\nCSeq: 1\r\n\r\n' >&3
        head -c 300 <&3" 2>/dev/null | grep -i "^Server:" | tr -d '\r')
    echo "  $cible : $SERVEUR"
done

echo
echo "=============================================================="
