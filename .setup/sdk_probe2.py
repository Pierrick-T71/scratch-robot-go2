"""Introspection du SDK installe.

Objectif : lever les points marques « a verifier » dans l'adaptateur, en
lisant le SDK REELlement installe plutot que la documentation.

Le canal doit etre initialise avant toute instanciation, sans quoi le
participant de domaine vaut None et le client echoue.
"""

import traceback

print("=== 1. initialisation du canal ===")
try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    ChannelFactoryInitialize(0, "eth0")
    print("  ChannelFactoryInitialize(0, 'eth0') : OK")
except Exception:
    print("  initialisation : ECHEC")
    traceback.print_exc()
    raise SystemExit(1)

print()
print("=== 2. methodes disponibles sur SportClient ===")
try:
    from unitree_sdk2py.go2.sport.sport_client import SportClient

    client = SportClient()
    print("  instanciation : OK")

    methodes = sorted(m for m in dir(client) if not m.startswith("_"))
    for m in methodes:
        print("   ", m)

    print()
    print("=== 3. reponses aux points « a verifier » ===")
    for nom in ("Move", "StopMove", "Sit", "RiseSit", "StandUp", "StandDown",
                "BalanceStand", "RecoveryStand", "Damp", "GetSportModeState",
                "GetLowState", "SetTimeout", "Init"):
        present = hasattr(client, nom)
        nature = ""
        if present:
            attr = getattr(client, nom)
            nature = "methode" if callable(attr) else "attribut"
        marque = "CONFIRME" if present else "ABSENT"
        print(f"  {nom:20s} {marque:9s} {nature}")
except Exception:
    print("  SportClient : ECHEC")
    traceback.print_exc()

print()
print("=== 4. signature de Move (nombre de parametres) ===")
try:
    import inspect
    from unitree_sdk2py.go2.sport.sport_client import SportClient
    src = inspect.getsource(SportClient.Move)
    print(src)
except Exception as exc:
    print("  lecture impossible :", exc)

print("=== 5. sujet DDS de l'etat ===")
try:
    from unitree_sdk2py.interface.sport import SportModeState
    print("  SportModeState : OK")
except Exception as exc:
    print("  SportModeState : ECHEC ->", exc)

