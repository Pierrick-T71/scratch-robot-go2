#!/bin/bash
# Balayage des configurations DDS possibles.
#
# On ne sait pas encore pourquoi le robot ne publie rien de visible. Ce script
# essaie les hypotheses dans l'ordre du plus probable :
#   A. la multidiffusion arrive (reference)
#   B. le robot ne repond qu'en unicast (point d'acces qui filtre)
#   C. le robot publie sur un autre domaine DDS

IP=${1:-172.16.8.11}
PY=/root/go2env311/bin/python
SONDE=/root/sonde_dds.py

lancer() {
    local titre="$1"; shift
    echo "########## $titre ##########"
    timeout 40 "$PY" "$SONDE" "$@" 2>&1 | grep -vE "^\[|^Traceback|cyclonedds" | head -14
    echo
}

lancer "A. domaine 0, multidiffusion"          0 -          eth0 8
lancer "B. domaine 0, pair unicast"            0 "$IP"      eth0 8
lancer "C. domaine 1, pair unicast"            1 "$IP"      eth0 8
lancer "D. domaine 2, pair unicast"            2 "$IP"      eth0 8
lancer "E. domaine 3, pair unicast"            3 "$IP"      eth0 8

echo "########## F. pendant ce temps, le robot emet-il en unicast vers nous ? ##########"
timeout 10 tcpdump -i eth0 -nn "host $IP" 2>/dev/null | head -10
echo "  (rien ci-dessus = le robot ne nous parle jamais spontanement)"
