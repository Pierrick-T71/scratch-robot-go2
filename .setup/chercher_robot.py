"""Recherche du robot sur le reseau.

Le robot Go2 publie en DDS et expose un SSH. On cherche donc :
  1. qui repond sur le port 22 dans le /21 ;
  2. la banniere SSH de chacun (un Go2 annonce Ubuntu, souvent un nom
     d'hote parlant) ;
  3. les adresses MAC anormales (codees en dur).

Aucune action offensive : uniquement des connexions TCP normales et une
lecture de banniere, comme le ferait un navigateur.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import sys

RESEAU = ipaddress.ip_network("172.16.8.0/21")
PORT = 22
CONCURRENCE = 300
DELAI = 1.5


async def banniere(ip: str) -> tuple[str, str] | None:
    try:
        lecteur, ecrivain = await asyncio.wait_for(
            asyncio.open_connection(ip, PORT), timeout=DELAI
        )
    except (OSError, asyncio.TimeoutError):
        return None

    texte = ""
    try:
        donnees = await asyncio.wait_for(lecteur.read(200), timeout=DELAI)
        # La console Windows est en cp1252 : on ne garde que l'ASCII
        # imprimable. Une banniere SSH n'apporte rien en Unicode.
        texte = donnees.decode("ascii", "replace").strip()
        texte = "".join(c if 32 <= ord(c) < 127 else "." for c in texte)
    except (OSError, asyncio.TimeoutError):
        pass
    finally:
        ecrivain.close()
        try:
            await asyncio.wait_for(ecrivain.wait_closed(), timeout=0.5)
        except Exception:
            pass

    return ip, texte


async def balayer() -> None:
    hotes = [str(h) for h in RESEAU.hosts()]
    print(f"  {len(hotes)} adresses a tester, port {PORT}, {CONCURRENCE} en parallele")
    print("  (environ 20 a 40 secondes)\n")

    semaphore = asyncio.Semaphore(CONCURRENCE)
    trouves: list[tuple[str, str]] = []

    async def tache(ip: str) -> None:
        async with semaphore:
            resultat = await banniere(ip)
            if resultat is not None:
                trouves.append(resultat)
                ip_t, texte = resultat
                print(f"  {ip_t:16s} {texte[:90]}", flush=True)

    await asyncio.gather(*(tache(ip) for ip in hotes))

    print(f"\n  {len(trouves)} machine(s) avec SSH ouvert.\n")

    print("=== signatures Unitree / robot ===")
    marqueurs = ("unitree", "go2", "go1", "b2", "quadruped", "jetson", "nvidia")
    for ip, texte in sorted(trouves):
        bas = texte.lower()
        if any(m in bas for m in marqueurs):
            print(f"  *** {ip} : {texte}")

    print("\n=== bannieres inhabituelles (ni Ubuntu standard ni Windows) ===")
    for ip, texte in sorted(trouves):
        if "ubuntu" not in texte.lower() and "openssh" not in texte.lower():
            print(f"  {ip:16s} {texte[:100]}")


if __name__ == "__main__":
    try:
        asyncio.run(balayer())
    except KeyboardInterrupt:
        sys.exit(1)
