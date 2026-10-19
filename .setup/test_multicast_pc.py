"""Le robot publie-t-il en DDS sur le Wi-Fi ?

TEST TEMOIN
-----------
Il ne suffit pas de constater « aucun paquet DDS ». Encore faut-il prouver
que le PC SAIT recevoir du multicast. On ecoute donc deux choses :

  - le SSDP (239.255.255.250:1900), dont on sait qu'il circule sur ce
    reseau : c'est le temoin ;
  - le DDS Unitree (239.255.0.1:7400+), la cible.

Si le temoin passe et que la cible reste muette, la conclusion est solide :
le robot ne publie pas en DDS sur le Wi-Fi.
"""

from __future__ import annotations

import socket
import struct
import time

TEMOIN = ("239.255.255.250", 1900)
CIBLES = [("239.255.0.1", p) for p in (7400, 7401, 7410, 7411)]
DUREE = 25


def ecouteur(groupe: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", port))
    except OSError:
        s.close()
        return None

    # On rejoint le groupe sur l'interface Wi-Fi, dont on connait l'adresse.
    rejoint = False
    for interface in ("172.16.12.50", "0.0.0.0"):
        try:
            mreq = struct.pack("4s4s", socket.inet_aton(groupe), socket.inet_aton(interface))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            rejoint = True
        except OSError:
            continue

    if not rejoint:
        s.close()
        return None

    s.settimeout(0.4)
    return s


print("=== temoin SSDP + recherche DDS (25 s) ===")
print()

temoin = ecouteur(*TEMOIN)
print(f"  temoin SSDP 239.255.255.250:1900 : {'ecoute' if temoin else 'IMPOSSIBLE'}")

cibles = {}
for groupe, port in CIBLES:
    e = ecouteur(groupe, port)
    if e is not None:
        cibles[(groupe, port)] = e
print(f"  cibles DDS                      : {len(cibles)} ecouteur(s)")
print()

compte_temoin = 0
compte_dds: dict[str, int] = {}
emetteurs_dds: set[str] = set()
debut = time.time()

while time.time() - debut < DUREE:
    if temoin is not None:
        try:
            if temoin.recvfrom(2048)[0]:
                compte_temoin += 1
        except (socket.timeout, OSError):
            pass

    for cle, s in cibles.items():
        try:
            donnees, adresse = s.recvfrom(65535)
        except (socket.timeout, OSError):
            continue
        if donnees:
            nom = f"{cle[0]}:{cle[1]}"
            compte_dds[nom] = compte_dds.get(nom, 0) + 1
            emetteurs_dds.add(adresse[0])

if temoin is not None:
    temoin.close()
for s in cibles.values():
    s.close()

print("=== resultat ===")
print(f"  temoin SSDP      : {compte_temoin} paquet(s)")
if compte_temoin == 0:
    print("    -> le PC ne recoit AUCUN multicast : test non concluant.")
    print("       (pare-feu Windows probablement en cause)")
else:
    print("    -> le PC recoit bien du multicast.")

print(f"  DDS Unitree      : {sum(compte_dds.values())} paquet(s)")
for nom, n in compte_dds.items():
    print(f"      {nom} : {n}")
if emetteurs_dds:
    print(f"    emetteurs : {sorted(emetteurs_dds)}")
elif compte_temoin > 0:
    print("    -> AUCUN paquet DDS : le robot ne publie pas en DDS sur ce reseau.")
