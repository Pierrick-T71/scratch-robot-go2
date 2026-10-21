#!/usr/bin/env python3
"""Trajectoire REELLE de chaque commande, lue dans les journaux existants.

Pour chaque deplacement on trace :
  - le cap (IMU) et la pose lidar ;
  - la position (odometrie et lidar) ;
  - la vitesse publiee par le robot.
et on cherche OU le robot s'est arrete (fin de la rotation).

Lecture seule : aucune commande n'est envoyee au robot.
"""
import json
import math
import re
from datetime import datetime, timedelta

LOG = "/root/go2/service.log"
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


etats = []       # (t, yaw, x, y, z, vx, vy, vz)
poses = []       # (t, yaw, x, y)
departs = []     # (t, kind, nominal, timeout)
premiere = []    # (t, ligne Move)

with open(LOG, "r", errors="replace") as f:
    for ligne in f:
        t, msg = parse_ts(ligne)
        if t is None:
            continue
        if "go2_service.adapters.webrtc: Deplacement " in msg:
            m = re.search(r"Deplacement (\w+) : vitesse ([-\d.]+) m/s, duree nominale ([\d.]+) s, delai d'arret ([\d.]+) s", msg)
            if m:
                departs.append((t, m.group(1), float(m.group(3)), float(m.group(4))))
            continue
        if "Premiere consigne Move" in msg:
            premiere.append((t, msg))
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
            yaw = float(rpy[2]) if len(rpy) >= 3 else None
            p = tuple(float(v) for v in pos[:3]) if len(pos) >= 3 else None
            v = tuple(float(x) for x in vel[:3]) if len(vel) >= 3 else None
            etats.append((t, yaw, p, v))
        elif topic == "rt/utlidar/robot_pose":
            p = data.get("pose") or {}
            pos = p.get("position") or {}
            ori = p.get("orientation") or {}
            if len(ori) >= 4:
                poses.append((t, yaw_quat(ori), float(pos.get("x", 0)), float(pos.get("y", 0))))


def etat_pres(t):
    v = None
    for e in etats:
        if e[0] <= t:
            v = e
        else:
            break
    return v


def pose_pres(t):
    v = None
    for e in poses:
        if e[0] <= t:
            v = e
        else:
            break
    return v


for t, kind, nominal, timeout in departs:
    print(f"===== {t.strftime('%H:%M:%S')} {kind} | nominal {nominal:.1f} s | delai d'arret {timeout:.1f} s =====")
    e0 = etat_pres(t)
    p0 = pose_pres(t)
    if e0 is None or p0 is None:
        print("   (pas d'etat)")
        continue
    y0, pos0 = e0[1], e0[2]
    ly0, lpos0 = p0[1], (p0[2], p0[3])
    print(f"   depart : cap IMU {math.degrees(y0):8.1f} | odom ({pos0[0]:7.2f},{pos0[1]:7.2f}) | lidar ({lpos0[0]:7.2f},{lpos0[1]:7.2f})")
    fin = None
    ech = t
    while ech <= t + timedelta(seconds=timeout + 8):
        e = etat_pres(ech)
        p = pose_pres(ech)
        if e is None or p is None:
            break
        rel = (ech - t).total_seconds()
        dcap = diff_deg(y0, e[1])
        dcap_l = diff_deg(ly0, p[1])
        dist = math.hypot(pos0[0] - e[2][0], pos0[1] - e[2][1]) * 100
        dist_l = math.hypot(lpos0[0] - p[2], lpos0[1] - p[3]) * 100
        v = e[3]
        vs = f"v=({v[0]:5.2f},{v[1]:5.2f},{v[2]:5.2f})" if v else ""
        if rel <= timeout + 4:
            print(f"   +{rel:5.2f}s  cap IMU {dcap:+8.1f}  cap lidar {dcap_l:+8.1f}  odom {dist:7.1f} cm  lidar {dist_l:7.1f} cm  {vs}")
        # Fin de rotation : la vitesse angulaire devient nulle ET le cap se stabilise.
        if fin is None and rel > nominal:
            vang = abs(v[2]) if v else 0.0
            if vang < 0.02:
                fin = (ech, dcap, dcap_l, dist, dist_l)
    if fin:
        print(f"   >>> ROTATION REELLE : IMU {fin[1]:+.1f} deg | lidar {fin[2]:+.1f} deg  (arret vers +{fin[0].strftime('%H:%M:%S')})")
    else:
        print("   >>> (la vitesse angulaire n'est jamais tombee a zero dans la fenetre)")
    print()
