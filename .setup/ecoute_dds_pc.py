"""Ecoute du trafic DDS depuis le PC de l'utilisateur.

CycloneDDS (le middleware d'Unitree) annonce ses participants sur le groupe
multidiffusion 239.255.0.1, ports 7400+ (7400 = decouverte du domaine 0).

Si un robot Go2 publie sur ce reseau, on doit voir des paquets sur ces ports.
C'est le test le plus direct : il ne depend d'aucun logiciel installe.
"""

from __future__ import annotations

import socket
import struct
import sys
import time

#: Groupes de decouverte CycloneDDS, du domaine 0 au domaine 3.
GROUPES = ("239.255.0.1", "239.255.0.2", "239.255.0.3", "239.255.0.4")

#: Ports DDS : decouverte (7400, 7410, ...) et donnees (7412, 7422, ...).
PORTS = (7400, 7410, 7420, 7430, 7440, 7412, 7422, 7432)

DUREE = 20


def ecouter(groupe: str, port: int) -> socket.socket | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", port))
    except OSError:
        s.close()
        return None

    # On rejoint le groupe sur TOUTES les interfaces disponibles.
    rejoint = False
    for interface in socket.gethostbyname_ex(socket.gethostname())[2] + ["0.0.0.0"]:
        try:
            mreq = struct.pack("4s4s", socket.inet_aton(groupe), socket.inet_aton(interface))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            rejoint = True
        except OSError:
            continue
    if not rejoint:
        s.close()
        return None

    s.settimeout(0.5)
    return s


def main() -> None:
    print("=== recherche de trafic DDS Unitree (20 s) ===")
    print("  groupe de decouverte 239.255.0.x, ports 7400-7440")
    print()

    sockets: dict[tuple[str, int], socket.socket] = {}
    for groupe in GROUPES:
        for port in PORTS:
            s = ecouter(groupe, port)
            if s is not None:
                sockets[(groupe, port)] = s

    print(f"  {len(sockets)} ecouteurs actifs")
    print()

    vus: dict[tuple[str, int], int] = {}
    emetteurs: set[str] = set()
    debut = time.time()

    while time.time() - debut < DUREE:
        for cle, s in sockets.items():
            try:
                donnees, adresse = s.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            if donnees:
                vus[cle] = vus.get(cle, 0) + 1
                emetteurs.add(adresse[0])
                if vus[cle] <= 2:
                    print(
                        f"  {cle[0]}:{cle[1]} <- {adresse[0]} ({len(donnees)} octets)",
                        flush=True,
                    )

    for s in sockets.values():
        s.close()

    print()
    print("=== resultat ===")
    if vus:
        print(f"  {sum(vus.values())} paquet(s) DDS recus")
        print(f"  emetteurs : {sorted(emetteurs)}")
        print()
        print("  => le robot publie sur ce reseau. Son adresse est ci-dessus.")
    else:
        print("  AUCUN paquet DDS recu en 20 s.")
        print()
        print("  => soit aucun robot ne publie en DDS sur ce reseau,")
        print("     soit le Wi-Fi ne laisse pas passer la multidiffusion.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
