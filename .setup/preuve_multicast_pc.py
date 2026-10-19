"""Preuve : le PC recoit-il du multicast d'AUTRES machines ?

Le test precedent comptait les paquets SSDP sans regarder qui les envoyait.
Or une machine entend aussi son propre trafic. Ce test enregistre donc
l'ADRESSE DE L'EMETTEUR de chaque paquet.

Si des adresses autres que la notre apparaissent, la reception multicast
du PC est prouvee. Si la cible DDS reste vide dans ce cas, alors le robot
ne publie pas en DDS sur ce Wi-Fi.
"""

from __future__ import annotations

import socket
import struct
import time
from collections import Counter

MON_IP = "172.16.12.50"
TEMOIN = ("239.255.255.250", 1900)          # SSDP : circule forcement
CIBLES = [(g, p) for g in ("239.255.0.1", "239.255.0.2") for p in (7400, 7401, 7410, 7411)]
DUREE = 30


def ecouteur(groupe: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", port))
    except OSError:
        s.close()
        return None

    rejoint = False
    for interface in (MON_IP, "0.0.0.0"):
        try:
            mreq = struct.pack("4s4s", socket.inet_aton(groupe), socket.inet_aton(interface))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            rejoint = True
        except OSError:
            continue
    if not rejoint:
        s.close()
        return None

    s.settimeout(0.3)
    return s


print("=== qui emet reellement sur ce Wi-Fi ? (30 s) ===")
print()

temoin = ecouteur(*TEMOIN)
print(f"  temoin SSDP : {'actif' if temoin else 'IMPOSSIBLE'}")
cibles = {cle: e for cle, e in ((c, ecouteur(*c)) for c in CIBLES) if e is not None}
print(f"  cibles DDS  : {len(cibles)} ecouteur(s) actif(s)")
print()

ssdp_emetteurs: Counter[str] = Counter()
dds_emetteurs: Counter[str] = Counter()
debut = time.time()

while time.time() - debut < DUREE:
    if temoin is not None:
        try:
            _, adresse = temoin.recvfrom(2048)
            ssdp_emetteurs[adresse[0]] += 1
        except (socket.timeout, OSError):
            pass
    for cle, s in cibles.items():
        try:
            donnees, adresse = s.recvfrom(65535)
        except (socket.timeout, OSError):
            continue
        if donnees:
            dds_emetteurs[adresse[0]] += 1

if temoin is not None:
    temoin.close()
for s in cibles.values():
    s.close()

print("=== SSDP : qui a parle ? ===")
for ip, n in ssdp_emetteurs.most_common(10):
    marque = "  <- notre PC" if ip == MON_IP else ""
    print(f"  {ip:16s} {n:4d} paquet(s){marque}")

autres = [ip for ip in ssdp_emetteurs if ip != MON_IP]
print()
if autres:
    print(f"  => {len(autres)} AUTRE(S) machine(s) entendue(s) : reception multicast prouvee.")
else:
    print("  => aucune autre machine : le PC n'entend que lui-meme.")
    print("     (le pare-feu Windows filtre probablement le multicast entrant)")

print()
print("=== DDS Unitree : qui a parle ? ===")
if dds_emetteurs:
    for ip, n in dds_emetteurs.most_common(10):
        print(f"  {ip:16s} {n:4d} paquet(s)")
    print("  => DU DDS EST PRESENT sur ce reseau !")
else:
    print("  aucun paquet DDS.")
    if autres:
        print("  => le robot ne publie PAS en DDS sur le Wi-Fi.")
