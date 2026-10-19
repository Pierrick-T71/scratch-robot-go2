"""Sonde DDS : balaie les ports de decouverte unicast d'un domaine.

POURQUOI CE SCRIPT
------------------
Un scan UDP classique ne dit rien ici : le noyau limite la production
d'ICMP a ~1/s, donc des ports fermes passent pour ouverts au hasard.

CycloneDDS, lui, accepte PLUSIEURS pairs unicast. On en declare un par
port candidat (7410 + 10*domaine + 2*index). S'il existe un participant
DDS sur l'un d'eux, il repond a notre annonce et les sujets arrivent.
Aucun ICMP n'est necessaire : la preuve est un message DDS recu.

USAGE
-----
    python sonde_dds_plage.py [domaine] [ip] [interface] [duree] [index_max]
"""

from __future__ import annotations

import sys
import threading
import time

DOMAINE = int(sys.argv[1]) if len(sys.argv) > 1 else 0
IP = sys.argv[2] if len(sys.argv) > 2 else "192.168.123.161"
INTERFACE = sys.argv[3] if len(sys.argv) > 3 else "eth0"
DUREE = float(sys.argv[4]) if len(sys.argv) > 4 else 10.0
INDEX_MAX = int(sys.argv[5]) if len(sys.argv) > 5 else 20

base = 7410 + 10 * DOMAINE
ports = [base + 2 * i for i in range(INDEX_MAX + 1)]
pairs = "".join(f'\n        <Peer address="{IP}:{port}"/>' for port in ports)
print(
    f"--- domaine {DOMAINE} | {len(ports)} ports {ports[0]}..{ports[-1]}"
    f" sur {IP} | {DUREE:g} s ---",
    flush=True,
)

import unitree_sdk2py.core.channel as ch  # noqa: E402

CONFIG = f'''<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS>
  <Domain Id="any">
    <General>
      <Interfaces>
        <NetworkInterface name="{INTERFACE}" priority="default" multicast="default"/>
      </Interfaces>
    </General>
    <Discovery>
      <Peers>{pairs}
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>'''

# La classe de fabrication lit le module a l'import : on remplace la constante
# dans SON espace de noms.
ch.ChannelConfigHasInterface = CONFIG

try:
    ch.ChannelFactoryInitialize(DOMAINE, INTERFACE)
except Exception as exc:
    print(f"    initialisation impossible : {type(exc).__name__}: {exc}", flush=True)
    sys.exit(1)

from unitree_sdk2py.idl.unitree_go.msg.dds_._SportModeState_ import (  # noqa: E402
    SportModeState_,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_._LowState_ import LowState_  # noqa: E402

TYPES = {
    "rt/sportmodestate": SportModeState_,
    "rt/lowstate": LowState_,
}

compteurs: dict[str, int] = {sujet: 0 for sujet in TYPES}
verrou = threading.Lock()
fabrique = ch.ChannelFactory()

for sujet, type_msg in TYPES.items():
    def fabriquer(nom: str):
        def _recu(_message):
            with verrou:
                compteurs[nom] += 1
        return _recu

    try:
        fabrique.CreateRecvChannel(sujet, type_msg, fabriquer(sujet), queueLen=16)
    except Exception as exc:
        print(f"    {sujet} : abonnement impossible ({exc})", flush=True)

debut = time.time()
vus: set[str] = set()
while time.time() - debut < DUREE:
    time.sleep(0.2)
    with verrou:
        for sujet, nombre in compteurs.items():
            if nombre and sujet not in vus:
                vus.add(sujet)
                print(f"    >>> {sujet} : PREMIER MESSAGE", flush=True)

with verrou:
    total = sum(compteurs.values())
    detail = dict(compteurs)

if total:
    print(f"    RESULTAT : {total} message(s) DDS recus", flush=True)
    for sujet, nombre in detail.items():
        if nombre:
            print(f"      {sujet} : {nombre}", flush=True)
else:
    print("    RESULTAT : aucun message DDS", flush=True)
