#!/bin/bash
# Analyse precise : le robot emet-il VRAIMENT quelque chose ?

IP=${1:-172.16.13.2}

echo "=== 1. paquets IP issus exactement du robot ==="
N=$(tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | grep -c "^..:..:..\.[0-9]* IP ${IP}\.")
echo "  $N"
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | grep " IP ${IP}\." | head -10

echo
echo "=== 2. ARP reellement emis par le robot ==="
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | grep -E "(${IP})\.?" | grep ARP | head -5
echo "  (ARP : champ 'who-has X tell Y' - X est l'emetteur)"

echo
echo "=== 3. multicast reel vs diffusion ==="
echo "  vraie multidiffusion (224-239) :"
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null \
  | grep -oE "> 2(2[4-9]|3[0-9])\.[0-9]+\.[0-9]+\.[0-9]+" | sort | uniq -c | sort -rn | head
echo "  diffusion (broadcast) :"
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null | grep -c "> 255\.255\.255\.255"

echo
echo "=== 4. quels hotes publient en multicast ? ==="
tcpdump -r /root/go2/capture.pcap -nn 2>/dev/null \
  | grep -oE "IP ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\.[0-9]+ > 2[2-9][0-9]\." \
  | sed -E 's/IP ([0-9.]+)\.[0-9]+ >/\1/' | sort | uniq -c | sort -rn | head

echo
echo "=== 5. ports ouverts sur le robot ==="
if command -v nmap >/dev/null; then
    nmap -Pn -p- --min-rate 2000 -T4 "$IP" 2>/dev/null | grep -E "^[0-9]+/tcp|^Nmap"
else
    echo "  nmap absent : test de quelques ports"
    for port in 22 80 443 7500 8000 8888; do
        timeout 2 bash -c "echo > /dev/tcp/$IP/$port" 2>/dev/null \
            && echo "    port $port OUVERT" || true
    done
fi

echo
echo "=== 6. le robot emet-il en unicast quand on le sollicite ? ==="
timeout 12 tcpdump -i eth0 -nn -c 60 "host $IP and greater 60" 2>/dev/null | head -20
echo "  (paquets de plus de 60 octets : une image DDS en ferait au moins plusieurs centaines)"