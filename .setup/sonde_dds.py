"""Sonde DDS : le robot repond-il, et sur quel domaine ?

CONTEXTE
--------
Le robot repond au ping mais n'emet AUCUN paquet visible depuis le conteneur.
Deux explications possibles :

  1. il publie en multidiffusion, mais le point d'acces Wi-Fi ne relaie pas
     la multidiffusion vers le reseau filaire (comportement tres courant) ;
  2. il ne publie pas du tout.

Le SDK Unitree utilise la multidiffusion pour la DECOUVERTE. Si elle est
filtree, aucune rencontre n'a lieu — meme si le robot va parfaitement bien.

PARADE
------
CycloneDDS accepte une liste de pairs en UNICAST. On annonce alors notre
presence directement a l'adresse du robot, ce qui contourne le probleme.

Ce script teste une configuration et sort. On l'appelle plusieurs fois avec
des domaines et des modes differents.
"""

from __future__ import annotations

import sys
import threading
import time

DOMAINE = int(sys.argv[1]) if len(sys.argv) > 1 else 0
PAIR = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
INTERFACE = sys.argv[3] if len(sys.argv) > 3 else "eth0"
DUREE = float(sys.argv[4]) if len(sys.argv) > 4 else 8.0

print(f"--- domaine {DOMAINE} | pair {PAIR or 'aucun'} | {DUREE:g} s ---", flush=True)

import unitree_sdk2py.core.channel as ch  # noqa: E402

# On reconstruit la configuration CycloneDDS.
# La difference tient en un bloc : <Discovery><Peers>.
decouverte = (
    f"""
    <Discovery>
      <Peers>
        <Peer address="{PAIR}"/>
      </Peers>
    </Discovery>"""
    if PAIR
    else """
    <Discovery>
      <ParticipantIndex>auto</ParticipantIndex>
    </Discovery>"""
)

CONFIG = f'''<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS>
  <Domain Id="any">
    <General>
      <Interfaces>
        <NetworkInterface name="{INTERFACE}" priority="default" multicast="default"/>
      </Interfaces>
    </General>{decouverte}
  </Domain>
</CycloneDDS>'''

# La classe de fabrication lit le module a l'import : on remplace la constante
# dans SON espace de noms, pas dans celui de channel_config.
ch.ChannelConfigHasInterface = CONFIG

try:
    ch.ChannelFactoryInitialize(DOMAINE, INTERFACE)
except Exception as exc:
    print(f"    initialisation impossible : {type(exc).__name__}: {exc}", flush=True)
    sys.exit(1)

# Sujets a surveiller. `rt/sportmodestate` porte la posture et le cap,
# `rt/lowstate` porte l'alimentation et les articulations.
SUJETS = ["rt/sportmodestate", "rt/lowstate", "rt/bmsstate", "rt/utlidar/lidar_state"]

from unitree_sdk2py.idl.unitree_go.msg.dds_._SportModeState_ import (  # noqa: E402
    SportModeState_,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_._LowState_ import LowState_  # noqa: E402

TYPES = {
    "rt/sportmodestate": SportModeState_,
    "rt/lowstate": LowState_,
}

compteurs: dict[str, int] = {s: 0 for s in SUJETS}
verrou = threading.Lock()

fabrique = ch.ChannelFactory()

for sujet, type_msg in TYPES.items():
    def fabriquer(s: str):
        def _recu(_message):
            with verrou:
                compteurs[s] += 1
        return _recu

    try:
        fabrique.CreateRecvChannel(sujet, type_msg, fabriquer(sujet), queueLen=16)
        print(f"    abonne a {sujet}", flush=True)
    except Exception as exc:
        print(f"    {sujet} : abonnement impossible ({exc})", flush=True)

debut = time.time()
vus: set[str] = set()
while time.time() - debut < DUREE:
    time.sleep(0.25)
    with verrou:
        for sujet, n in compteurs.items():
            if n > 0 and sujet not in vus:
                vus.add(sujet)
                print(f"    >>> {sujet} : PREMIER MESSAGE recu", flush=True)

with verrou:
    total = sum(compteurs.values())

if total:
    print(f"    RESULTAT : {total} message(s) DDS recus", flush=True)
    for sujet, n in compteurs.items():
        if n:
            print(f"      {sujet} : {n}", flush=True)
else:
    print("    RESULTAT : aucun message DDS", flush=True)
