#!/usr/bin/env python3
"""Mesure REALISTE de chaque commande, a partir des journaux existants.

Deux mesures independantes :
  - l'IMU du robot   (rt/lf/sportmodestate -> imu_state.rpy[2])
  - la pose du lidar (rt/utlidar/robot_pose -> orientation quaternion)
Et deux mesures de position :
  - l'odometrie du robot (sportmodestate -> position)
  - la position du lidar (robot_pose -> position)

Aucune commande n'est envoyee : lecture seule du journal.
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


imu = []        # (t, yaw)
pose = []       # (t, yaw, x, y)
odom = []       # (t, x, y)
departs = []    # (t, kind, nominal, timeout)
stops = []      # t

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
            if len(rpy) >= 3:
                imu.append((t, float(rpy[2])))
            pos = data.get("position") or []
            if len(pos) >= 3:
                odom.append((t, float(pos[0]), float(pos[1])))
        elif topic == "rt/utlidar/robot_pose":
            p = (data.get("pose") or {})
            pos = p.get("position") or {}
            ori = p.get("orientation") or {}
            if len(ori) >= 4:
                pose.append((t, yaw_quat(ori), float(pos.get("x", 0)), float(pos.get("y", 0))))

print(f"IMU : {len(imu)}   pose lidar : {len(pose)}   odom : {len(odom)}")
print()


def imu_pres(t):
    v = None
    for e in imu:
        if e[0] <= t:
            v = e
        else:
            break
    return v


def pose_pres(t):
    v = None
    for e in pose:
        if e[0] <= t:
            v = e
        else:
            break
    return v


def imu_apres(t):
    for e in imu:
        if e[0] >= t:
            return e
    return None


def pose_apres(t):
    for e in pose:
        if e[0] >= t:
            return e
    return None


for t, kind, nominal, timeout in departs:
    fin = next((s for s in stops if s >= t), None)
    duree_reelle = (fin - t).total_seconds() if fin else float("nan")
    i0 = imu_pres(t)
    i1 = imu_pres(fin) if fin else None
    p0 = pose_pres(t)
    p1 = pose_pres(fin) if fin else None
    o0 = odom[-1] if odom else None
    o1 = odom[-1] if odom else None

    ligne = f"{t.strftime('%H:%M:%S')} {kind:13s} nominal {nominal:5.1f} s  timeout {timeout:5.1f} s"
    if i0 and i1:
        ligne += f" | IMU {math.degrees(i0[1]):7.1f}->{math.degrees(i1[1]):7.1f} ({diff_deg(i0[1], i1[1]):+7.1f})"
    if p0 and p1:
        ligne += f" | LIDAR {math.degrees(p0[1]):7.1f}->{math.degrees(p1[1]):7.1f} ({diff_deg(p0[1], p1[1]):+7.1f})"
        d = math.hypot(p1[2] - p0[2], p1[3] - p0[3])
        ligne += f" | pos lidar {d*100:6.1f} cm"
    print(ligne)

print()
print("=== detail d'une rotation : cap IMU et cap lidar, et position ===")
for t, kind, nominal, timeout in departs:
    if not kind.startswith("turn"):
        continue
    fin = next((s for s in stops if s >= t), None)
    if fin is None:
        continue
    print(f"--- {t.strftime('%H:%M:%S')} {kind} nominal {nominal:.1f} s, timeout {timeout:.1f} s, arret {fin.strftime('%H:%M:%S')} ---")
    i0 = imu_pres(t)
    p0 = pose_pres(t)
    ech = t
    while ech <= fin + timedelta(seconds=1.0):
        i = imu_pres(ech)
        p = pose_pres(ech)
        rel = (ech - t).total_seconds()
        si = f"{diff_deg(i0[1], i[1]):+8.1f}" if (i and i0) else "      ? "
        sp = f"{diff_deg(p0[1], p[1]):+8.1f}" if (p and p0) else "      ? "
        dp = f"{(math.hypot(p[2]-p0[2], p[3]-p0[3])*100):6.1f}" if (p and p0) else "     ?"
        print(f"   +{rel:5.2f}s  IMU {si} deg   LIDAR {sp} deg   deplacement {dp} cm")
        ech += timedelta(seconds=0.5)
    print()
