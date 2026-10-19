#!/bin/bash
# Diagnostic de connexion au robot. STRICTEMENT LECTURE.
#
# Ce script ne commande RIEN : ni mouvement, ni posture, ni vitesse. Il se
# contente de repondre a trois questions, dans l'ordre :
#
#   1. le robot repond-il sur le reseau ?
#   2. le canal DDS s'ouvre-t-il ?
#   3. l'etat du robot remonte-t-il reellement ?
#
# Toute donnee absente est signalee ABSENTE. Aucune valeur n'est devinee :
# une batterie non lue ne vaut pas 0.

ROBOT_IP="${1:-}"
IFACE="${2:-eth0}"
VENV=/root/go2env311
TIMEOUT_S=12

if [ -z "$ROBOT_IP" ]; then
    echo "Usage : $0 <ip-du-robot> [interface-reseau]"
    echo "Exemple : $0 172.16.13.100 eth0"
    exit 64
fi

echo "################################################"
echo "# GO2 Scratch - etat de la connexion au robot"
echo "################################################"
echo "robot vise  : $ROBOT_IP"
echo "interface   : $IFACE"
echo "mode        : LECTURE SEULE (aucune commande envoyee)"
echo

# ---------------------------------------------------------------- reseau
echo "=== 1. RESEAU ==="
if ping -c 2 -W 2 "$ROBOT_IP" >/dev/null 2>&1; then
    echo "  ping        : REPOND"
else
    echo "  ping        : SANS REPONSE"
    echo
    echo "  -> Verifiez le cable, l'adresse, et que le robot est demarre."
    echo "  -> Si le ping passe mais pas le SDK, le multicast est bloque."
    exit 1
fi

# ------------------------------------------------- multicast et interface
echo
echo "=== 2. MULTICAST (DDS) ==="
if ip maddr show dev "$IFACE" 2>/dev/null | grep -q "224.0.0.1"; then
    echo "  $IFACE     : abonne au multicast 224.0.0.1"
else
    echo "  $IFACE     : ATTENTION, pas d'abonnement multicast visible"
fi

# ------------------------------------------------------ ouverture du DDS
echo
echo "=== 3. CANAL DDS ==="
export ROBOT_IP
timeout "$TIMEOUT_S" "$VENV/bin/python" - "$IFACE" <<'PYEOF' || echo "  canal DDS : ECHEC (voir message ci-dessus)"
import sys
iface = sys.argv[1]
try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelFactoryRelease
except Exception as exc:
    print(f"  SDK introuvable : {exc}")
    sys.exit(1)

try:
    ChannelFactoryInitialize(0, iface)
    print(f"  canal DDS : OUVERT sur {iface}")
except Exception as exc:
    print(f"  canal DDS : ECHEC -> {type(exc).__name__}: {exc}")
    sys.exit(1)

# ------------------------------------------------------- lecture d'etat
print()
print("=== 4. ETAT DU ROBOT (lecture) ===")
try:
    from unitree_sdk2py.g1.g1 import G1SportClient

    client = G1SportClient()
    client.SetTimeout(3000)
    client.Init()
    print("  client      : connecte")

    etat = client.GetLowState()
    if etat is None:
        print("  etat        : AUCUNE DONNEE")
        print()
        print("  -> Le canal s'ouvre mais aucun message n'arrive.")
        print("     Causes probables : multicast non route, robot en mode")
        print("     different, ou mauvais sous-reseau.")
    else:
        print("  etat        : RECU")
        # Une valeur absente est notée ABSENTE, jamais remplacée par 0.
        batterie = getattr(etat, "bms", None)
        vbat = getattr(batterie, "voltage", None) if batterie else None
        print(f"  tension     : {vbat if vbat is not None else 'NON MESUREE'}")
        soc = getattr(batterie, "SOC", None) if batterie else None
        print(f"  batterie   : {soc if soc is not None else 'NON MESUREE'} %")
        print(f"  boot state  : {getattr(etat, 'tick', 'inconnu')}")
except Exception as exc:
    print(f"  lecture     : ECHEC -> {type(exc).__name__}: {exc}")

try:
    ChannelFactoryRelease()
except Exception:
    pass
PYEOF

echo
echo "################################################"
echo "# Fin du diagnostic. Aucun mouvement commande."
echo "################################################"