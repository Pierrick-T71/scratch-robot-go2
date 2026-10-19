"""Ou se lit l'etat du robot ?

`SportClient` n'a ni GetLowState ni GetSportModeState : l'etat passe par un
ABONNE DDS. Ce probe cherche le bon objet et le bon sujet.
"""

import traceback

from unitree_sdk2py.core.channel import ChannelFactoryInitialize

ChannelFactoryInitialize(0, "eth0")
print("canal ouvert")
print()

print("=== SportModeState : ou est-il ? ===")
cible = None
for mod in (
    "unitree_sdk2py.idl.unitree_hg.msg.dds_",
    "unitree_sdk2py.g1.g1",
    "unitree_sdk2py.go2.sport",
):
    try:
        m = __import__(mod, fromlist=["*"])
        noms = [n for n in dir(m) if "SportModeState" in n or "LowState" in n]
        print(f"  {mod} : {noms[:8]}")
        if "SportModeState" in noms and cible is None:
            cible = getattr(m, "SportModeState")
    except Exception as exc:
        print(f"  {mod} : ECHEC {type(exc).__name__}")

print()
print("=== sous-modules du paquet idl ===")
try:
    import pkgutil
    import unitree_sdk2py.idl as idl
    for m in pkgutil.walk_packages(idl.__path__, "unitree_sdk2py.idl."):
        if "sport" in m.name.lower() or "g2" in m.name.lower() or "default" in m.name.lower():
            print("   ", m.name)
except Exception as exc:
    print("  ECHEC", exc)

print()
print("=== G1SportClient (état et batterie) ===")
try:
    from unitree_sdk2py.g1.g1 import G1SportClient
    c = G1SportClient()
    print("  methodes :", sorted(m for m in dir(c) if not m.startswith("_")))
except Exception:
    traceback.print_exc()

print()
print("=== abonnements disponibles ===")
try:
    import unitree_sdk2py.idl.default as dflt
    print("  topics :", sorted(n for n in dir(dflt) if not n.startswith("_"))[:30])
except Exception as exc:
    print("  ECHEC", type(exc).__name__, exc)