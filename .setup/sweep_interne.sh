#!/bin/bash
# Le robot est en mode routeur (3 reseaux).
#
# Question : depuis le conteneur, voit-on SEULEMENT la patte interne du
# routeur (192.168.123.161), ou bien tout le reseau interne du robot ?
#
#   - seul .161 repond  -> routeur NAT : l'interieur du robot est cache,
#                          et le DDS reste injoignable par ce chemin.
#   - plusieurs reponses -> reseau interne route : on peut y chercher le DDS.

set -u

echo "### 1. adresse et routes du conteneur"
ip -brief addr show eth0
ip route
echo

echo "### 2. le robot repond-il ?"
ping -c 2 -W 2 172.16.8.11 | grep -E "bytes from"
echo

if ip route get 192.168.123.161 2>/dev/null | grep -q "via 172.16.8.11"; then
    echo "### route interne deja en place"
else
    echo "### route interne absente : ajout"
    ip route add 192.168.123.0/24 via 172.16.8.11 2>&1 | sed 's/^/  /'
fi
echo

echo "### 3. balayage de 192.168.123.0/24 (on n'affiche que ce qui repond)"
seq 1 254 | xargs -P 64 -I{} sh -c '
    r=$(ping -c 1 -W 1 192.168.123.{} 2>/dev/null | grep -o "ttl=[0-9]*")
    [ -n "$r" ] && echo "  192.168.123.{}  $r"
'
echo

echo "### 4. autres reseaux possibles du robot"
for cible in 192.168.12.1 192.168.12.161 192.168.12.99 10.0.0.1; do
    r=$(ping -c 1 -W 1 "$cible" 2>/dev/null | grep -o "ttl=[0-9]*")
    if [ -n "$r" ]; then echo "  $cible  $r"; else echo "  $cible  muet"; fi
done
echo

echo "### 5. empreinte du robot"
ip neigh show 172.16.8.11 | sed 's/^/  /'
echo
echo "### fin"
