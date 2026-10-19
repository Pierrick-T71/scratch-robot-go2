import inspect
import time
import traceback

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, Channel

ChannelFactoryInitialize(0, "eth0")
print("canal ouvert\n")

print("=== signature de Channel ===")
print(" ", inspect.signature(Channel.__init__))

from unitree_sdk2py.idl.unitree_go.msg.dds_._SportModeState_ import SportModeState_

print("\n=== champs de SportModeState_ ===")
noms = [n for n in dir(SportModeState_) if not n.startswith("_")]
print(" ", noms[:25])

print("\n=== abonnement (6 s) ===")
try:
    recu = {"oui": False, "msg": None}
    canal = Channel(0, "rt/sportmodestate", SportModeState_)
    canal.Init(1, lambda m: recu.update(oui=True, msg=m))
    print("  abonnement : cree sur rt/sportmodestate")

    debut = time.time()
    while time.time() - debut < 6 and not recu["oui"]:
        time.sleep(0.2)

    if recu["oui"]:
        m = recu["msg"]
        print("  message    : RECU")
        imu = getattr(m, "imu", None)
        print("  imu.rpy    :", getattr(imu, "rpy", "absent") if imu else "absent")
        pos = getattr(m, "position", None)
        print("  position   :", list(pos) if pos else "absent")
        mode = getattr(m, "mode", None)
        if mode is not None:
            print("  mode.prs   :", getattr(mode, "prs", "absent"))
            print("  mode.foot  :", getattr(mode, "foot", "absent"))
            print("  mode.state :", getattr(mode, "state", "absent"))
    else:
        print("  message    : AUCUN en 6 s")
        print("  -> multicast non route, ou robot absent du sous-reseau")
except Exception:
    traceback.print_exc()