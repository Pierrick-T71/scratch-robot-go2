"""Premier contact WebRTC avec le robot : ecoute seule.

Aucune commande n'est envoyee. On se connecte au canal de l'app mobile
(port 9991) et on s'abonne a l'etat du sport mode. Si des messages
arrivent, le chemin de commande existe et fonctionne en Wi-Fi.

Le robot refuse la connexion si un autre client est deja maitre
(l'app mobile ouverte, par exemple) : RobotBusyError.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.FATAL)

from unitree_webrtc_connect import (  # noqa: E402
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
    RTC_TOPIC,
)

IP = sys.argv[1] if len(sys.argv) > 1 else "172.16.8.11"
DUREE = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
# Cle AES-128 propre au robot (firmware Go2 >= 1.1.15). Fournie en variable
# d'environnement pour ne pas la laisser dans l'historique des commandes.
CLE = os.environ.get("UNITREE_AES_128_KEY") or (sys.argv[3] if len(sys.argv) > 3 else None)

recus = 0


def sur_etat(message):
    global recus
    recus += 1
    if recus <= 3:
        donnees = message.get("data") or {}
        print(
            f"  message {recus} : mode={donnees.get('mode')} "
            f"position={donnees.get('position')} "
            f"vitesse={donnees.get('velocity')}",
            flush=True,
        )


async def principal():
    print(f"### connexion a {IP} (canal WebRTC, port 9991)", flush=True)
    connexion = UnitreeWebRTCConnection(
        WebRTCConnectionMethod.LocalSTA, ip=IP, aes_128_key=CLE
    )
    try:
        await connexion.connect()
    except Exception as erreur:  # noqa: BLE001 - on veut le type exact
        print(f"### ECHEC {type(erreur).__name__} : {erreur}", flush=True)
        return

    print("### CONNECTE au canal du robot", flush=True)
    connexion.datachannel.pub_sub.subscribe(RTC_TOPIC["LF_SPORT_MOD_STATE"], sur_etat)

    await asyncio.sleep(DUREE)
    print(f"### {recus} message(s) d'etat recus en {DUREE:g} s", flush=True)

    try:
        await connexion.disconnect()
    except Exception:  # noqa: BLE001 - fermeture best effort
        pass


asyncio.run(principal())
