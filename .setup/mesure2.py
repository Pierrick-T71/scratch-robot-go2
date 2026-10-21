#!/usr/bin/env python3
"""Mesure PRECISE, sur les journaux existants, de ce que fait chaque ordre.

Aucune commande n'est envoyee au robot : lecture seule du journal.

Pour chaque commande on determine :
  - quand la rotation/avancement commence vraiment ;
  - l'angle (IMU ET pose lidar) et la distance AU MOMENT de l'arret ;
  - l'angle et la distance 3 s PLUS TARD (debordement apres l'arret).
"""
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


etats = []
poses = []
departs = []
stops = []

with open(LOG, "r", errors="replace") as f:
    for ligne in f:
        t, msg = parse_ts(ligne)
        if t is None:
            continue
        if "go2_service.adapters.webrtc: Deplacement " in msg:
            m = re.search(
                r"Deplacement (\w+) : vitesse ([-\d.]+) m/s, duree nominale ([\d.]+) s, delai d'arret ([\d.]+) s",
                msg,
            )
            if m:
                departs.append((t, m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))))
            continue
        if "Commande envoyee au robot : StopMove" in msg:
            stops.append(t)
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
                    (float(vel[2]) if len(vel) >= 3 else 0.0),
                    (float(vel[0]) if len(vel) >= 3 else 0.0),
                )
            )
        elif topic == "rt/utlidar/robot_pose":
            p = data.get("pose") or {}
            pos = p.get("position") or {}
            ori = p.get("orientation") or {}
            if len(ori) >= 4:
                poses.append((t, yaw_quat(ori), float(pos.get("x", 0)), float(pos.get("y", 0))))


def etat_pres(t):
    lo, hi, v = 0, len(etats) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if etats[mid][0] <= t:
            v = etats[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return v


def pose_pres(t):
    lo, hi, v = 0, len(poses) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if poses[mid][0] <= t:
            v = poses[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return v


lignes = []
for t, kind, vitesse, nominal, timeout in departs:
    e0 = etat_pres(t)
    p0 = pose_pres(t)
    if e0 is None or p0 is None:
        continue
    fin = next((s for s in stops if s >= t), None)
    if fin is None:
        continue
    y0, pos0 = e0[1], e0[2]
    ly0, lpos0 = p0[1], (p0[2], p0[3])

    # Etat a l'arret et 3 s plus tard.
    ea = etat_pres(fin)
    pa = pose_pres(fin)
    e3 = etat_pres(fin + timedelta(seconds=3))
    p3 = pose_pres(fin + timedelta(seconds=3))

    # Instant ou le mouvement commence vraiment (IMU ou odom qui bouge).
    depart_reel = None
    for e in etats:
        if t <= e[0] <= fin:
            if abs(diff_deg(y0, e[1])) > 3.0 or math.hypot(e[2][0] - pos0[0], e[2][1] - pos0[1]) > 0.03:
                depart_reel = e[0]
                break

    def dec(e, p):
        if e is None or p is None:
            return "     ?      ?       ?      ?"
        d_cap = diff_deg(y0, e[1])
        d_cap_l = diff_deg(ly0, p[1])
        dist = math.hypot(e[2][0] - pos0[0], e[2][1] - pos0[1]) * 100
        dist_l = math.hypot(p[2] - lpos0[0], p[3] - lpos0[1]) * 100
        return f"{d_cap:+8.1f} {d_cap_l:+8.1f} {dist:7.1f} {dist_l:7.1f}"

    lignes.append(f"===== {t.strftime('%H:%M:%S')} {kind} | vitesse {vitesse:+.2f} m/s | nominal {nominal:.1f} s | timeout {timeout:.1f} s")
    if depart_reel:
        lignes.append(f"      demarrage reel : +{(depart_reel - t).total_seconds():.1f} s")
    else:
        lignes.append("      demarrage reel : AUCUN mouvement")
    lignes.append(f"      A L'ARRET (+{(fin - t).total_seconds():.1f} s)  cap IMU  cap lidar  odom    lidar : {dec(ea, pa)}")
    lignes.append(f"      3 s APRES L'ARRET                     cap IMU  cap lidar  odom    lidar : {dec(e3, p3)}")
    lignes.append("")

with open(SORTIE, "w", encoding="utf-8") as f:
    f.write("\n".join(lignes))
print(f"{len(lignes)} lignes -> {SORTIE}")
