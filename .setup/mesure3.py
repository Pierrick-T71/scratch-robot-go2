#!/usr/bin/env python3
"""MESURE REELLE des commandes, lue dans les journaux existants.

Lecture seule : aucune commande n'est envoyee au robot.

Pour chaque ordre on trouve :
  t0 = instant de la premiere consigne Move ;
  t1 = instant du premier StopMove STRICTEMENT apres t0 (l'arret) ;
puis on relit l'etat du robot (cap IMU, pose lidar, position, vitesse) a t0,
a t1, et 1/2/3/5 s apres t1 (le debordement apres l'arret).
"""
import bisect
import json
import math
import re
from datetime import datetime, timedelta

LOG = "/root/go2/service.log"
SORTIE = "/root/mesure.txt"
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+\w+\s+(.*)$")


def parse_ts(ligne):
    m = TS.match(ligne)
    if not m:
        return None, None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f"), m.group(2)


def doc_json(texte):
    i = texte.find('{"type":"msg"')
    if i < 0:
        return None
    try:
        return json.loads(texte[i:])
    except Exception:
        return None


def yaw_quat(q):
    x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def diff_deg(a, b):
    return math.degrees((b - a + math.pi) % (2 * math.pi) - math.pi)


etats = []   # t, yaw, (x,y), (vx,vy,vz)
poses = []   # t, yaw, x, y
premier = [] # t, kind, vitesse, nominal, timeout
stops = []   # t

with open(LOG, "r", errors="replace") as f:
    for ligne in f:
        t, msg = parse_ts(ligne)
        if t is None:
            continue
        if "Premiere consigne Move" in msg:
            m = re.search(r"x=([-\d.]+) y=([-\d.]+) z=([-\d.]+) m/s", msg)
            if m:
                premier.append((t, (float(m.group(1)), float(m.group(2)), float(m.group(3)))))
            continue
        if "Commande envoyee au robot : StopMove" in msg:
            stops.append(t)
            continue
        if "go2_service.adapters.webrtc: Deplacement " in msg:
            m = re.search(
                r"Deplacement (\w+) : vitesse ([-\d.]+) m/s, duree nominale ([\d.]+) s, delai d'arret ([\d.]+) s",
                msg,
            )
            if m:
                premier.append(
                    (t, ("DEPL", m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))))
                )
            continue
        if "Received message on data channel" not in msg:
            continue
        d = doc_json(msg)
        if not d:
            continue
        topic = d.get("topic", "")
        data = d.get("data") or {}
        if topic == "rt/lf/sportmodestate":
            rpy = (data.get("imu_state") or {}).get("rpy") or []
            pos = data.get("position") or []
            vel = data.get("velocity") or []
            if len(rpy) < 3 or len(pos) < 3:
                continue
            etats.append(
                (
                    t,
                    float(rpy[2]),
                    (float(pos[0]), float(pos[1])),
                    (float(vel[0]), float(vel[1]), float(vel[2])) if len(vel) >= 3 else (0.0, 0.0, 0.0),
                )
            )
        elif topic == "rt/utlidar/robot_pose":
            p = data.get("pose") or {}
            pos = p.get("position") or {}
            ori = p.get("orientation") or {}
            if len(ori) >= 4:
                poses.append((t, yaw_quat(ori), float(pos.get("x", 0)), float(pos.get("y", 0))))


def au_plus_proche(liste, ts, t):
    i = bisect.bisect_right([e[0] for e in liste], t) - 1
    if i < 0:
        return None
    return liste[i]


sortie = []
for t0, info in premier:
    if info[0] != "DEPL":
        continue
    kind, vitesse, nominal, timeout = info[1], info[2], info[3], info[4]
    # Premier StopMove STRICTEMENT apres t0.
    i = bisect.bisect_right(stops, t0)
    if i >= len(stops):
        continue
    t1 = stops[i]
    e0 = au_plus_proche(etats, None, t0)
    p0 = au_plus_proche(poses, None, t0)
    if e0 is None or p0 is None:
        continue
    y0, pos0, v0 = e0[1], e0[2], e0[3]
    ly0, lpos0 = p0[1], (p0[2], p0[3])

    sortie.append(
        f"===== {t0.strftime('%H:%M:%S.%f')[:-3]} {kind} | consigne {vitesse:+.2f} m/s | nominal {nominal:.1f} s | timeout {timeout:.1f} s"
    )
    sortie.append(f"      consigne envoyee {t0.strftime('%H:%M:%S.%f')[:-3]}  arret {t1.strftime('%H:%M:%S.%f')[:-3]}  -> DUREE REELLE {(t1 - t0).total_seconds():.2f} s")
    for libelle, tt in (("t0 consigne", t0), ("t1 arret    ", t1), ("t1 +1 s     ", t1 + timedelta(seconds=1)),
                        ("t1 +2 s     ", t1 + timedelta(seconds=2)), ("t1 +3 s     ", t1 + timedelta(seconds=3)),
                        ("t1 +5 s     ", t1 + timedelta(seconds=5))):
        e = au_plus_proche(etats, None, tt)
        p = au_plus_proche(poses, None, tt)
        if e is None or p is None:
            continue
        d_cap = diff_deg(y0, e[1])
        d_cap_l = diff_deg(ly0, p[1])
        dist = math.hypot(e[2][0] - pos0[0], e[2][1] - pos0[1]) * 100
        dist_l = math.hypot(p[2] - lpos0[0], p[3] - lpos0[1]) * 100
        v = e[3]
        sortie.append(
            f"      {libelle}  cap IMU {d_cap:+8.1f}  cap LIDAR {d_cap_l:+8.1f}  odom {dist:7.1f} cm  lidar {dist_l:7.1f} cm  v=({v[0]:5.2f},{v[1]:5.2f},{v[2]:5.2f})"
        )
    sortie.append("")

with open(SORTIE, "w", encoding="utf-8") as f:
    f.write("\n".join(sortie))
print(f"{len(sortie)} lignes -> {SORTIE}")
