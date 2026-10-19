import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def essai(payload, label):
    req = urllib.request.Request(
        BASE + "/api/robot/connect",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    debut = time.time()
    try:
        rep = urllib.request.urlopen(req, timeout=60)
        print(f"  {label} : HTTP {rep.status} en {time.time()-debut:.1f}s")
        print("   ", rep.read().decode()[:300])
    except urllib.error.HTTPError as e:
        print(f"  {label} : HTTP {e.code} en {time.time()-debut:.1f}s")
        print("   ", e.read().decode()[:300])
    except Exception as e:
        print(f"  {label} : {type(e).__name__} {e}")


print("=== le service annonce-t-il encore un faux positif ? ===")
essai(
    {
        "robot_ip": "172.16.13.100",
        "network_interface": "eth0",
        "lancer_test": False,
    },
    "IP sans robot, connexion seule",
)

print()
print("=== mode apres echec : simulation conservee ? ===")
with urllib.request.urlopen(BASE + "/api/status", timeout=10) as rep:
    statut = json.load(rep)
print("  mode     :", statut["mode"])
print("  connected:", statut["connected"])

print()
print("=== deconnexion ===")
req = urllib.request.Request(
    BASE + "/api/robot/disconnect", data=b"{}", method="POST"
)
with urllib.request.urlopen(req, timeout=10) as rep:
    print("  ", rep.read().decode())