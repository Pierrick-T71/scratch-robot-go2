#!/usr/bin/env python3
"""Verite terrain, lue dans le journal existant. Aucune commande envoyee.

On utilise l'horodatage DU ROBOT (stamp) plutot que l'heure de lecture :
c'est la seule horloge qui ne soit pas perturbee par la saturation de la
boucle. On en deduit :
  - le debit angulaire et lineaire REELS ;
  - la latence entre l'horodatage du robot et la reception du message.
"""
import json
import math
import re
from datetime import datetime

LOG = "/root/go2/service.log"
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+\w+\s+(.*)$")

echantillons = []   # (t_local, t_robot, yaw, x, y)
departs = []        # (t_local, kind, nominal)

with open(LOG, "r", errors="replace") as f:
    for ligne in f:
        m = TS.match(ligne)
        if not m:
            continue
        t_local = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f")
        msg = m.group(2)
        if "go2_service.adapters.webrtc: Deplacement " in msg:
            d = re.search(r"Deplacement (\w+) :", msg)
            if d:
                departs.append((t_local, d.group(1)))
            continue
        if "Received message on data channel" not in msg:
            continue
        i = msg.find('{"type":"msg"')
        if i < 0:
            continue
        try:
            doc = json.loads(msg[i:])
        except Exception:
            continue
        if doc.get("topic") != "rt/lf/sportmodestate":
            continue
        data = doc.get("data") or {}
        stamp = data.get("stamp") or {}
        rpy = (data.get("imu_state") or {}).get("rpy") or []
        pos = data.get("position") or []
        if len(rpy) < 3 or len(pos) < 3 or "sec" not in stamp:
            continue
        t_robot = stamp["sec"] + stamp.get("nanosec", 0) / 1e9
        echantillons.append(
            (t_local.timestamp(), t_robot, float(rpy[2]), float(pos[0]), float(pos[1]))
        )

print(f"echantillons : {len(echantillons)}")

# --- latence : heure locale de lecture moins horodatage du robot -----------
latences = []
for t_local, t_robot, *_ in echantillons:
    latences.append(t_local - t_robot)
latences.sort()
print(
    "latence lecture (s) : min %.2f  median %.2f  p90 %.2f  max %.2f"
    % (
        latences[0],
        latences[len(latences) // 2],
        latences[int(len(latences) * 0.9)],
        latences[-1],
    )
)

# --- debit reel, par fenetre de commande ----------------------------------
print()
print("debit reel mesure (horloge du robot) :")
for t_local, kind in departs:
    # Fenetre de 12 s a partir du depart, dans l'horloge du robot.
    bornes = [e for e in echantillons if t_local.timestamp() - 6 <= e[0] <= t_local.timestamp() + 20]
    if len(bornes) < 20:
        continue
    t0 = bornes[0]
    fin = bornes[-1]
    dt = fin[1] - t0[1]
    if dt <= 0:
        continue
    dyaw = 0.0
    for a, b in zip(bornes, bornes[1:]):
        d = (b[2] - a[2] + math.pi) % (2 * math.pi) - math.pi
        dyaw += d
    dlin = math.hypot(fin[3] - t0[3], fin[4] - t0[4])
    print(
        f"  {t_local.strftime('%H:%M:%S')} {kind:14s} dt_robot {dt:5.2f} s"
        f"  debit {math.degrees(dyaw) / dt:+7.2f} deg/s"
        f"  lineaire {dlin / dt:6.3f} m/s"
    )
