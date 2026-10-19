#!/bin/bash
# Diagnostic de l'environnement avant installation.
# Lecture seule : aucune modification.

echo "=== SYSTEME ==="
cat /etc/os-release | head -2
uname -r
echo "hote: $(hostname)"

echo
echo "=== PYTHON ==="
python3 --version 2>&1
python3 -c "import ensurepip; print('ensurepip disponible')" 2>&1

echo
echo "=== PIP ==="
command -v pip3 >/dev/null && echo "pip3: present" || echo "pip3: ABSENT"
python3 -m pip --version 2>&1 | head -1
command -v apt-get >/dev/null && echo "apt-get: present" || echo "apt-get: ABSENT"

echo
echo "=== INTERFACES RESEAU ==="
echo "partagees avec l'hote Proxmox, car le conteneur LXC n'a pas de pile propre"
ip -br addr

echo
echo "=== ROUTAGE ==="
ip route

echo
echo "=== LIAISON CABLEE ==="
for i in $(ls /sys/class/net); do
  if [ -d "/sys/class/net/$i/wireless" ]; then
    echo "$i = SANS FIL"
  else
    echo "$i = CABLE"
  fi
done

echo
echo "=== MULTICAST ==="
ip maddr show 2>/dev/null | head -8
sysctl net.ipv4.conf.all.mc_forwarding 2>/dev/null

echo
echo "=== OUTILS DE COMPILATION ==="
for c in git gcc g++ make cmake; do
  command -v $c >/dev/null && echo "$c: present" || echo "$c: ABSENT"
done

echo
echo "=== PARE-FEU ==="
command -v iptables >/dev/null && echo "iptables: present" || echo "iptables: absent"
command -v nft >/dev/null && echo "nft: present" || echo "nft: absent"

echo
echo "=== ESPACE DISQUE ==="
df -h / | tail -1

echo
echo "=== SDK UNITREE DEJA INSTALLE ? ==="
python3 -c "import unitree_sdk2py; print('SDK deja present')" 2>&1 | tail -1