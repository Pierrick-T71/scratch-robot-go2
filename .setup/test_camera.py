#!/usr/bin/env python3
"""Le robot envoie-t-il sa camera sur ce canal WebRTC ?

Test de faisabilite, hors service : on se connecte, on demande la video, et
on compte les images recues.
"""
from __future__ import annotations

import asyncio
import io
import os

import av

from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)


async def main() -> None:
    cle = os.environ.get("GO2_ROBOT_AES_KEY", "")
    print("cle presente :", bool(cle))

    connexion = UnitreeWebRTCConnection(
        WebRTCConnectionMethod.LocalSTA,
        ip="172.16.8.11",
        aes_128_key=cle,
    )
    await connexion.connect()
    print("connecte")

    compteur = {"n": 0}

    async def lecteur(track) -> None:
        print("piste recue :", track.kind)
        try:
            while True:
                image = await track.recv()
                if compteur["n"] < 3:
                    tampon = io.BytesIO()
                    conteneur = av.open(tampon, mode="w", format="mjpeg")
                    flux = conteneur.add_stream("mjpeg", rate=1)
                    flux.width = image.width
                    flux.height = image.height
                    flux.pix_fmt = "yuvj420p"
                    for paquet in flux.encode(image):
                        conteneur.mux(paquet)
                    conteneur.close()
                    print(
                        f"  image {compteur['n']} : {image.width}x{image.height} "
                        f"jpeg={len(tampon.getvalue())} octets"
                    )
                compteur["n"] += 1
        except Exception as exc:  # noqa: BLE001
            print("fin du flux :", type(exc).__name__, exc)
        finally:
            print("images recues :", compteur["n"])

    connexion.video.add_track_callback(lecteur)
    connexion.video.switchVideoChannel(True)
    print("video demandee")

    await asyncio.sleep(12)
    print("fin du test")


if __name__ == "__main__":
    asyncio.run(main())
