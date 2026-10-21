#!/usr/bin/env python3
"""Reconstruit, depuis les journaux existants, ce que le robot a REALLY fait.

Aucune commande n'est envoyee : on ne LIT que service.log.

Pour chaque deplacement on regarde :
  - l'instant de depart (ligne « Deplacement ... » du service) ;
  - l'instant de fin (ligne « Commande envoyee au robot : StopMove ») ;
  - le cap (imu_state.rpy[2]) et la position (odometrie) publies par le robot.
"""
import json
import math
import re
import sys
from datetime import datetime

LOG = "/root/go2/service.log"

TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+\w+\s+(.*)$")


def parse_ts(ligne):
    m = TS.match(ligne)
    if not m:
        return None, None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f"), m.group(2)


def extraire_json(texte):
    """Le SDK journalise une ligne 'Received message on data channel: {json}'."""
    i = texte.find('{"type":"msg"')
    if i < 0:
        return None
    try:
        return json.loads(texte[i:])
    except Exception:
        return None


def diff_ang_deg(a, b):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return math.degrees(d)


etats = []          # (t, yaw, x, y, z)
departs = []        # (t, kind, ligne)
stops = []          # (t, ligne)

with open(LOG, "r", errors="replace") as f:
    for ligne in f:
        t, msg = parse_ts(ligne)
        if t is None:
            continue
        if "go2_service.adapters.webrtc: Deplacement " in msg:
            departs.append((t, msg))
        elif "Commande envoyee au robot : StopMove" in msg:
            stops.append(t)
        elif "Received message on data channel" in msg and "sportmodestate" in msg:
            doc = extraire_json(msg)
            if not doc:
                continue
            data = doc.get("data") or {}
            imu = data.get("imu_state") or {}
            rpy = imu.get("rpy") or []
            pos = data.get("position") or []
            yaw = float(rpy[2]) if len(rpy) >= 3 else None
            p = tuple(float(v) for v in pos[:3]) if len(pos) >= 3 else None
            etats.append((t, yaw, p))


def etat_au_plus_proche(t):
    """Dernier etat connu a l'instant t (et le suivant)."""
    avant = None
    for e in etats:
        if e[0] <= t:
            avant = e
        else:
            break
    return avant


def etats_entre(t0, t1):
    return [e for e in etats if t0 <= e[0] <= t1]


print(f"etats sportmodestate lus : {len(etats)}")
print(f"deplacements             : {len(departs)}")
print(f"arrets (StopMove)        : {len(stops)}")
print()

for t, msg in departs:
    genre = re.search(r"Deplacement (\w+) : vitesse ([-\d.]+) m/s, duree nominale ([\d.]+) s", msg)
    if not genre:
        continue
    kind = genre.group(1)
    duree_nominale = float(genre.group(3))
    # Instant de fin : premier StopMove apres le depart.
    fin = next((s for s in stops if s >= t), None)
    if fin is None:
        fin = t
    duree_reelle = (fin - t).total_seconds()

    dep = etat_au_plus_proche(t)
    fin_etat = etat_au_plus_proche(fin)
    yaw0 = dep[1] if dep else None
    yaw1 = fin_etat[1] if fin_etat else None
    p0 = dep[2] if dep else None
    p1 = fin_etat[2] if fin_etat else None

    ligne = f"{t.strftime('%H:%M:%S')} {kind:13s} nominal {duree_nominale:5.1f} s | reel {duree_reelle:5.1f} s"
    if yaw0 is not None and yaw1 is not None:
        ligne += f" | cap {math.degrees(yaw0):7.1f} -> {math.degrees(yaw1):7.1f} ({diff_ang_deg(yaw0, yaw1):+7.1f} deg)"
    else:
        ligne += " | cap ?"
    if p0 and p1:
        d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        ligne += f" | odom {d * 100:6.1f} cm"
    print(ligne)

print()
print("=== detail : cap et odometrie pendant chaque deplacement ===")
for t, msg in departs:
    genre = re.search(r"Deplacement (\w+) :", msg)
    if not genre:
        continue
    kind = genre.group(1)
    fin = next((s for s in stops if s >= t), None)
    if fin is None:
        fin = t
    fenetre = etats_entre(t, fin + __import__("datetime").timedelta(seconds=0.5))
    if not fenetre:
        continue
    print(f"--- {t.strftime('%H:%M:%S')} {kind}  ({len(fenetre)} etats) ---")
    for e in fenetre[:40]:
        yaw = f"{math.degrees(e[1]):7.1f}" if e[1] is not None else "   ?  "
        p = e[2]
        ps = f"({p[0]:7.2f},{p[1]:7.2f},{p[2]:6.2f})" if p else ""
        rel = (e[0] - t).total_seconds()
        print(f"   +{rel:5.2f}s  yaw {yaw}  odom {ps}")
    if len(fenetre) > 40:
        print(f"   ... {len(fenetre) - 40} etats de plus")
