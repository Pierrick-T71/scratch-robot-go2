#!/bin/bash
# Le robot emet-il quelque chose sur le reseau ?
#
# Question decisive : on regarde le trafic REEL de l'interface pendant que le
# SDK ecoute. Si on voit des paquets du robot qui n'ont rien a voir avec nos
# pings, le robot emet et quelque chose bloque le multicast. Si on ne voit que
# les reponses a nos propres pings, le robot n'emet aucun trafic periodique.

set -u
IP=${1:-172.16.13.2}
DUREE=${2:-15}

export DEBIAN_FRONTEND=noninteractive
command -v tcpdump >/dev/null || apt-get install -y -qq --no-install-recommends tcpdump

echo "=== observation de $DUREE s sur eth0 ==="
echo "  filtre : tout ce qui vient de $IP ou qui est du multicast"
echo

# L'ecoute SDK demarre en parallele : c'est elle qui provoque un eventuel
# trafic du robot vers nous.
/root/go2env311/bin/python - "$IP" > /root/go2/ecoute_sdk.log 2>&1 <<'PYEOF' &
import sys, time
try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    ChannelFactoryInitialize(0, "eth0")
    print("canal ouvert, ecoute en cours", flush=True)
    time.sleep(20)
except Exception as exc:
    print("erreur:", exc, flush=True)
PYEOF

PID_ECOUTE=$!
sleep 1

tcpdump -i eth0 -nn -c 400 -w /root/go2/capture.pcap "host $IP or multicast" >/dev/null 2>&1 &
PID_TCPDUMP=$!

sleep "$DUREE"
kill $PID_TCPDUMP 2>/dev/null
wait $PID_ECOUTE 2>/dev/null

echo
echo "=== ce qui a ete capture ==="
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | head -40
echo
echo "=== resume ==="
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | wc -l | xargs echo "  paquets captures :"
echo
echo "=== paquets MULTICAST uniquement ==="
MULTI=$(tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | grep -c " > 224\.\| > 239\.")
echo "  $MULTI"
if [ "$MULTI" -gt 0 ]; then
    echo "  -> le multicast ARRIVE sur l'interface."
    echo "     Si le SDK ne reçoit rien, le sujet publie est peut-etre different."
else
    echo "  -> le multicast N'ARRIVE PAS sur l'interface."
    echo "     Le blocage est en amont : pont Proxmox ou point d'acces Wi-Fi."
fi