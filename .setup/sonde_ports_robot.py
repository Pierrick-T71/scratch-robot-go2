"""Sonde : le robot expose-t-il encore son canal ? (lecture seule, aucun envoi)"""

from __future__ import annotations

import socket
import subprocess
import time

CIBLE = "172.16.8.11"
PORTS = (8551, 8081, 9991)


def ping() -> str:
    sortie = subprocess.run(
        ["ping", "-c", "3", "-W", "2", CIBLE],
        capture_output=True,
        text=True,
        check=False,
    )
    return sortie.stdout.strip().splitlines()[-1] if sortie.stdout.strip() else "aucune reponse"


def tcp(port: int) -> str:
    prise = socket.socket()
    prise.settimeout(3)
    debut = time.monotonic()
    try:
        prise.connect((CIBLE, port))
        return f"OUVERT ({(time.monotonic() - debut) * 1000:.0f} ms)"
    except Exception as erreur:  # noqa: BLE001
        return f"ferme ({type(erreur).__name__})"
    finally:
        prise.close()


print(f"=== ping {CIBLE} ===")
print(" ", ping())

print(f"=== ports TCP de {CIBLE} ===")
for port in PORTS:
    print(f"  {port} : {tcp(port)}")
