import importlib
import pkgutil
import traceback

print("=== 1. paquet go2 ===")
try:
    import unitree_sdk2py.go2 as go2
    print("  unitree_sdk2py.go2 : OK")
except Exception as exc:
    print("  unitree_sdk2py.go2 : ECHEC", exc)

print()
print("=== 2. chemin utilise par le service ===")
try:
    from unitree_sdk2py.go2.sport.sport_client import SportClient
    print("  SportClient : OK ->", SportClient)
    cl = SportClient()
    print("  methodes :", sorted(m for m in dir(cl) if not m.startswith("_"))[:30])
except Exception:
    print("  SportClient : ECHEC")
    traceback.print_exc()

print()
print("=== 3. ce que contient unitree_sdk2py ===")
import unitree_sdk2py
print("  version :", getattr(unitree_sdk2py, "__version__", "?"))
for mod in pkgutil.walk_packages(unitree_sdk2py.__path__, "unitree_sdk2py."):
    print("   ", mod.name)