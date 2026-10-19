"""Joue un fichier audio sur le haut-parleur du Go2.

Le son passe par la piste audio WebRTC : c'est le meme canal que l'app
mobile utilise pour parler dans le robot. Aucune commande de mouvement
n'est envoyee.

On mesure ce qui SORT reellement (octets audio transmis) : si ce compteur
reste a zero, le son n'a pas ete envoye, quelle que soit l'impression.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.ERROR)

from aiortc.contrib.media import MediaPlayer  # noqa: E402

from unitree_webrtc_connect import (  # noqa: E402
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)

IP = sys.argv[1]
FICHIER = sys.argv[2]
DUREE = float(sys.argv[3]) if len(sys.argv) > 3 else 40.0
CLE = os.environ.get("UNITREE_AES_128_KEY")


async def octets_audio(connexion) -> int:
    """Total d'octets audio deja transmis vers le robot."""
    total = 0
    for rapport in (await connexion.pc.getStats()).values():
        if getattr(rapport, "type", "") != "outbound-rtp":
            continue
        if getattr(rapport, "kind", "") != "audio":
            continue
        total += int(getattr(rapport, "bytesSent", 0) or 0)
    return total


async def principal() -> None:
    connexion = UnitreeWebRTCConnection(
        WebRTCConnectionMethod.LocalSTA, ip=IP, aes_128_key=CLE
    )
    await connexion.connect()
    print("### canal etabli", flush=True)

    # Dire au robot de rester a l'ecoute de ce que le canal lui envoie.
    try:
        connexion.datachannel.switchAudioChannel(True)
        print("### canal audio du robot ouvert", flush=True)
    except Exception as erreur:  # noqa: BLE001
        print(f"### bascule audio impossible : {erreur}", flush=True)

    lecteur = MediaPlayer(FICHIER)
    piste = lecteur.audio
    if piste is None:
        print("### ffmpeg n'a pas pu ouvrir le fichier audio", flush=True)
        return

    connexion.pc.addTrack(piste)
    print("### piste audio ajoutee a la connexion", flush=True)

    boucle = asyncio.get_running_loop()
    debut = boucle.time()
    precedent = 0
    while boucle.time() - debut < DUREE:
        await asyncio.sleep(2.0)
        total = await octets_audio(connexion)
        debit = (total - precedent) / 2.0
        precedent = total
        ecoule = boucle.time() - debut
        print(
            f"  t={ecoule:5.1f}s  audio envoye={total:9d} octets  ({debit/1024:6.1f} Ko/s)",
            flush=True,
        )

    print("### fin de la diffusion", flush=True)


asyncio.run(principal())
