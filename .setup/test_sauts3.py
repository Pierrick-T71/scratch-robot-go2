#!/usr/bin/env python3
"""Le robot décolle-t-il vraiment ?

Deux signaux :
- les efforts dans les pieds, lus dans l'etat BAS (les vrais) ;
- l'acceleration verticale : une impulsion forte = la patented des pattes.
"""
from __future__ import annotations

import asyncio
import os

from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)

COMMANDES = {
    "FrontJump": 1031,
    "FrontPounce": 1032,
    "Bound": 1304,
}


async def main() -> None:
    cle = os.environ.get("GO2_ROBOT_AES_KEY", "")
    connexion = UnitreeWebRTCConnection(
        WebRTCConnectionMethod.LocalSTA,
        ip="172.16.8.11",
        aes_128_key=cle,
    )
    await connexion.connect()
    print("connecte")

    etats: list[dict] = []

    def sur_etat(message) -> None:
        donnees = (message or {}).get("data") or {}
        if "imu_state" not in donnees:
            return
        imu = donnees.get("imu_state") or {}
        accel = imu.get("accelerometer") or [0, 0, 0]
        etats.append(
            {
                "az": accel[2] if len(accel) > 2 else 0.0,
                "z": (donnees.get("position") or [0, 0, 0])[2],
            }
        )

    def sur_bas(message) -> None:
        donnees = (message or {}).get("data") or {}
        if "foot_force" not in donnees:
            return
        etats.append({"pieds": donnees.get("foot_force") or []})

    connexion.datachannel.pub_sub.subscribe("rt/lf/sportmodestate", sur_etat)
    connexion.datachannel.pub_sub.subscribe("rt/lf/lowstate", sur_bas)

    for nom, api_id in COMMANDES.items():
        print()
        print(f"=== {nom} (api_id {api_id}) ===")
        etats.clear()
        await asyncio.sleep(1.0)
        await connexion.datachannel.pub_sub.publish_request_new(
            "rt/api/sport/request", {"api_id": api_id, "parameter": ""}
        )
        await asyncio.sleep(5.0)

        appuis = [e["pieds"] for e in etats if "pieds" in e]
        accels = [e["az"] for e in etats if "az" in e]
        zs = [e["z"] for e in etats if "z" in e]
        if appuis:
            totaux = [sum(p) for p in appuis]
            print(f"  appuis au sol (2 Hz) : {len(totaux)} echantillons, "
                  f"min {min(totaux)} max {max(totaux)}")
            faibles = [t for t in totaux if t < 60]
            print(f"  echantillons ou les pieds ne portent plus : {len(faibles)}")
        if accels:
            print(f"  acceleration verticale : min {min(accels):.1f}  max {max(accels):.1f} m/s2")
        if zs:
            print(f"  hauteur estimee (z) : min {min(zs):.3f}  max {max(zs):.3f}  (debout ~0.32)")

    await connexion.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
