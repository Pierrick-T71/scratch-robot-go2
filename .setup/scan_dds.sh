#!/bin/bash
# Quels ports DDS sont ouverts sur une adresse ?
#
# Un socket UDP "connecte" remonte l'ICMP port-unreachable sous forme
# d'erreur : c'est ainsi qu'on distingue ferme / ouvert.
# Les envois sont espaces de 1,1 s car le noyau limite la production
# d'ICMP a environ un par seconde : sans cela, des ports fermes
# passeraient pour ouverts.

set -u
CIBLE="${1:?usage: scan_dds.sh <ip> [debut] [fin]}"
DEBUT="${2:-7400}"
FIN="${3:-7480}"

python3 - "$CIBLE" "$DEBUT" "$FIN" <<'PY'
import socket
import sys
import time

cible, debut, fin = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
print(f"### ports DDS {debut}-{fin} sur {cible}")

interessants = []
for port in range(debut, fin + 1):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    try:
        s.connect((cible, port))
        s.send(b"\x00" * 20)
    except OSError as erreur:
        s.close()
        print(f"  {port} : envoi impossible ({erreur})")
        continue

    try:
        s.recv(2048)
        statut = "REPONSE"
    except socket.timeout:
        statut = "ouvert ou filtre"
    except ConnectionRefusedError:
        statut = "ferme"
    except OSError as erreur:
        statut = f"erreur {erreur}"
    s.close()

    if statut != "ferme":
        print(f"  {port} : {statut}")
        interessants.append(port)
    time.sleep(1.1)

print()
if interessants:
    print(f"### a creuser : {interessants}")
else:
    print("### tout ferme : aucun service DDS sur cette adresse")
PY
