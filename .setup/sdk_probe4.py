"""Sujet exact de l'etat du robot, et abonne de demonstration.

`unitree_sdk2py.idl.unitree_go.msg.dds_` contient `_SportModeState_`.
Ce probe verifie le TYPE et tente un abonnement avec un delai court.
"""

import time
import traceback

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, Channel

ChannelFactoryInitialize(0, "eth0")
print("canal ouvert\n")

print("=== type SportModeState_ ===")
from unitree_sdk2py.idl.unitree_go.msg import dds_ as go2_dds

type_msg = getattr(go2_dds, "_SportModeState_", None)
print("  _SportModeState_ :", type_msg)
if type_msg is not None:
    noms = [n for n in dir(type_msg) if not n.startswith("_")]
    print("  champs :", noms[:20])

print()
print("=== abonnement a rt/sportmodestate (delai 6 s) ===")
try:
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import _SportModeState_

    canal = Channel("rt/sportmodestate", _SportModeState_)
    canal.Init(1, lambda m: None)
    print("  abonnement : cree")

    recu = {"oui": False, "msg": None}
    canal.Init(1, lambda m: recu.update(oui=True, msg=m))

    debut = time.time()
    while time.time() - debut < 6:
        time.sleep(0.2)

    if recu["oui"]:
        m = recu["msg"]
        print("  message    : RECU")
        print("  imu.rpy    :", getattr(getattr(m, "imu", None), "rpy", "absent"))
        print("  position   :", getattr(m, "position", "absent"))
        print("  velocity   :", getattr(m, "velocity", "absent"))
        mode = getattr(m, "mode", None)
        if mode is not None:
            print("  mode       :", [a for a in dir(mode) if not a.startswith("_")][:14])
            print("  mode.prs   :", getattr(mode, "prs", None))
            print("  mode.foot  :", getattr(mode, "foot", None))
    else:
        print("  message    : AUCUN recu en 6 s")
        print()
        print("  -> soit le robot est absent du reseau,")
        print("     soit le multicast n'est pas route sur ce chemin.")
except Exception:
    traceback.print_exc()