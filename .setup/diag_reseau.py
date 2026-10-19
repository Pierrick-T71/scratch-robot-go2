"""Diagnostic du chemin reseau vers le robot.

Le robot repond au ping mais aucun message DDS n'arrive. Il faut savoir
OU le multicast est bloque : conteneur, hote Proxmox, ou liaison sans fil.
"""

import socket
import struct
import subprocess
import sys
import threading
import time

IP = sys.argv[1] if len(sys.argv) > 1 else "172.16.13.2"
IFACE = sys.argv[2] if len(sys.argv) > 2 else "eth0"

print("=" * 62)
print(f"  Diagnostic reseau vers {IP} via {IFACE}")
print("=" * 62)


def lire(cmd):
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except Exception as exc:
        return f"<erreur {exc}>"


print("\n=== 1. LE ROBOT REPOND-IL ? ===")
sortie = lire(f"ping -c 3 -W 2 {IP}")
print(sortie[-400:] if sortie else "  <aucune sortie>")

print("\n=== 2. CHEMIN VERS LE ROBOT ===")
print(lire(f"ip route get {IP}"))
print("\n  table de routage :")
print(lire("ip route"))

print("\n=== 3. INTERFACE ET MULTICAST ===")
print(lire(f"ip -br addr show {IFACE}"))
print()
print("  drapeaux de l'interface :")
print(lire(f"ip -d link show {IFACE} | head -12"))
print()
print("  groupes multicast :")
print(lire(f"ip maddr show dev {IFACE}"))

print("\n=== 4. PARE-FEU ===")
print("  nft :")
print(lire("nft list ruleset 2>/dev/null | head -40") or "    (vide ou indisponible)")
print("  iptables :")
print(lire("iptables -S 2>/dev/null | head -20") or "    (vide ou indisponible)")

print("\n=== 5. UN AUTRE MESSAGE MULTICAST PASSE-T-IL ? ===")
"""
On ecoute 224.0.0.1 pendant 5 s avec une socket brute.
Si le groupe systeme ne passe pas, le multicast est coupe plus bas.
"""
recu = []


def ecoute():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except OSError:
        pass
    s.bind(("224.0.0.1", 0))
    s.settimeout(5)
    try:
        while True:
            data, addr = s.recvfrom(65535)
            if data:
                recu.append((addr, len(data)))
                return
    except socket.timeout:
        return
    finally:
        s.close()


t = threading.Thread(target=ecoute, daemon=True)
t.start()
t.join(6)
print(
    f"  224.0.0.1 : {len(recu)} message(s) recu(s)"
    + (f" depuis {recu[0][0]}" if recu else "  <- le multicast NE PASSE PAS")
)

print("\n=== 6. LE ROBOT PUBLIE-T-IL SUR UN AUTRE SUJET ? ===")
"""
Le robot peut publier ailleurs. On ecoute les ports et adresses multidiffusion
connus de l'ecosysteme Unitree pour voir si quelque chose arrive.
"""
vif = []
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
except OSError:
    pass
s.settimeout(6)
# Les groupes Unitree usuels.
for groupe in ("239.77.0.1", "224.0.0.185", "239.77.0.0"):
    try:
        mreq = struct.pack("4sl", socket.inet_aton(groupe), socket.INADDR_ANY)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        vif.append(groupe)
    except OSError as e:
        print(f"  abonnement impossible sur {groupe} : {e}")
print(f"  groupes rejoints : {', '.join(vif) if vif else 'aucun'}")

debut = time.time()
trouve = 0
try:
    while time.time() - debut < 6:
        data, addr = s.recvfrom(65535)
        if data:
            trouve += 1
            if trouve <= 5:
                print(f"  recu {len(data):>5} octets depuis {addr[0]}")
except socket.timeout:
    pass
finally:
    s.close()

if trouve:
    print(f"  => {trouve} message(s) DDS recus : le multicast PASSE")
else:
    print("  => AUCUN message DDS recu : le multicast est coupe AILLEURS")
    print("     (pont Proxmox, hote, ou routeur Wi-Fi)")

print("\n" + "=" * 62)