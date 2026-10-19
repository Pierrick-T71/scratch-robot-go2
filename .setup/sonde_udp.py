"""Sonde UDP corrigee : quels ports DDS sont ouverts ?

CORRECTION IMPORTANTE
---------------------
Un socket UDP NON connecte ne recoit jamais les messages ICMP : le noyau ne
sait pas a qui les attribuer. Il faut donc `connect()` le socket pour que
l'erreur « port unreachable » remonte.

Sans cette correction, tous les ports paraissent silencieux — y compris les
ports fermes. C'est ce qui a fausse le premier essai.
"""

from __future__ import annotations

import errno
import socket
import sys
import time

CIBLES = sys.argv[1:] or ["172.16.8.11", "192.168.123.161"]
DEBUT, FIN = 7400, 7450


def tester(cible: str, port: int) -> str:
    """Renvoie 'ferme', 'ouvert' ou 'erreur'."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.6)
    try:
        s.connect((cible, port))
    except OSError:
        s.close()
        return "erreur"

    try:
        s.send(b"\x00" * 24)
        try:
            s.recv(1024)
        except socket.timeout:
            return "ouvert"  # personne ne s'est plaint
        except ConnectionRefusedError:
            return "ferme"
        except OSError as exc:
            if exc.errno == errno.ECONNREFUSED:
                return "ferme"
            return "ouvert"
        return "ouvert"
    except ConnectionRefusedError:
        return "ferme"
    except OSError as exc:
        if exc.errno == errno.ECONNREFUSED:
            return "ferme"
        return "erreur"
    finally:
        s.close()


for cible in CIBLES:
    print(f"=== {cible} ===")
    resultats: dict[str, list[int]] = {"ouvert": [], "ferme": [], "erreur": []}
    for port in range(DEBUT, FIN + 1):
        resultats[tester(cible, port)].append(port)

    for etat in ("ouvert", "ferme", "erreur"):
        ports = resultats[etat]
        if not ports:
            continue
        plages: list[str] = []
        debut_plage = precedent = ports[0]
        for p in ports[1:]:
            if p == precedent + 1:
                precedent = p
                continue
            plages.append(
                f"{debut_plage}-{precedent}" if debut_plage != precedent else str(debut_plage)
            )
            debut_plage = precedent = p
        plages.append(
            f"{debut_plage}-{precedent}" if debut_plage != precedent else str(debut_plage)
        )
        print(f"  {etat:8s} ({len(ports):2d}) : {', '.join(plages)}")
    print()
    time.sleep(0.5)
