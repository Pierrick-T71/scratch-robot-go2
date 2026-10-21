#!/usr/bin/env python3
"""Debits REELS du chien, mesures sur l'horloge DU ROBOT.

Pour chaque episode de mouvement, on prend les echantillons consecutifs
(IMU + pose lidar) et on en deduit le debit median, puis la derive
pendant l'arret. Lecture seule du journal.
"""
import json
import math
import re
import statistics
from datetime import datetime

LOG = "/root/go2/service.log"
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+\w+\s+(.*)$")


def parse_ts(ligne):
    m = TS.match(ligne)
    if not m:
        return None, None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f"), m.group(2)


imu = []    # (t_robot, yaw, x, y)
pose = []   # (t_robot, yaw, x, y)
moves = []  # (t_local, x, y, z)

with open(LOG, "r", errors="replace") as f:
    for ligne in f:
        t_local, msg = parse_ts(ligne)
        if t_local is None:
            continue
        if "Premier" in msg and "consigne Move" in msg:
            m = re.search(r"x=([-\d.]+) y=([-\d.]+) z=([-\d.]+)", msg)
            if m:
                moves.append((t_local, float(m.group(1)), float(m.group(2)), float(m.group(3))))
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
        topic = doc.get("topic", "")
        data = doc.get("data") or {}
        if topic == "rt/lf/sportmodestate":
            stamp = data.get("stamp") or {}
            if "sec" not in stamp:
                continue
            t = stamp["sec"] + stamp.get("nanosec", 0) / 1e9
            rpy = (data.get("imu_state") or {}).get("rpy") or []
            pos = data.get("position") or []
            if len(rpy) >= 3 and len(pos) >= 3:
                imu.append((t, float(rpy[2]), float(pos[0]), float(pos[1])))
        elif topic == "rt/utlidar/robot_pose":
            stamp = (data.get("header") or {}).get("stamp") or {}
            if "sec" not in stamp:
                continue
            t = stamp["sec"] + stamp.get("nanosec", 0) / 1e9
            p = data.get("pose") or {}
            ori = p.get("orientation") or {}
            pos = p.get("position") or {}
            if len(ori) >= 4:
                yaw = math.atan2(
                    2 * (ori["w"] * ori["z"] + ori["x"] * ori["y"]),
                    1 - 2 * (ori["y"] ** 2 + ori["z"] ** 2),
                )
                pose.append((t, yaw, float(pos.get("x", 0)), float(pos.get("y", 0))))

imu.sort(key=lambda e: e[0])
pose.sort(key=lambda e: e[0])


def debit_yaw(echantillons, t0, t1):
    """Degres par seconde, median des echantillons consecutifs."""
    fenetre = [e for e in echantillons if t0 <= e[0] <= t1]
    rates = []
    for a, b in zip(fenetre, fenetre[1:]):
        dt = b[0] - a[0]
        if 0.02 < dt < 0.2:
            d = (b[1] - a[1] + math.pi) % (2 * math.pi) - math.pi
            rates.append(math.degrees(d) / dt)
    return statistics.median(rates) if rates else None, len(rates)


def debit_lineaire(echantillons, t0, t1):
    fenetre = [e for e in echantillons if t0 <= e[0] <= t1]
    rates = []
    for a, b in zip(fenetre, fenetre[1:]):
        dt = b[0] - a[0]
        if 0.02 < dt < 0.2:
            d = math.hypot(b[2] - a[2], b[3] - a[3])
            rates.append(d / dt)
    return statistics.median(rates) if rates else None, len(rates)


print("=== episodes de mouvement (horloge du robot) ===")
print("debut      fin        debit yaw   debit lineaire  derive apres arret")
for i, (t_local, vx, vy, vz) in enumerate(moves):
    if vz == 0 and vx == 0 and vy == 0:
        continue
    # fenetre du mouvement : de la premiere a la derniere consigne de CE type.
    meme = [m for m in moves if m[3] == vz and m[1] == vx and m[2] == vy]
    meme = [m for m in meme if m[0] >= t_local - __import__("datetime").timedelta(seconds=1)]
    if not meme:
        continue
    fin_locale = meme[-1][0]
    # horloge robot : on prend les echantillons autour de la fenetre locale,
    # traduite en temps robot via les horodatages locaux des echantillons.
    if not imu:
        break
    base_locale, base_robot = imu[0][0], None
    # correspondence locale -> robot : on prend le premier echantillon.
    paires = []
    for e in imu:
        paires.append(e)
    # t_local de depart converti : on cherche l'echantillon robot le plus proche
    # du premier echantillon apres la fenetre locale (les messages sont lus
    # dans l'ordre, et le decalage local->robot est stable).
    etat_local = []
    with open(LOG, "r", errors="replace") as f:
        for ligne in f:
            tl, msg = parse_ts(ligne)
            if tl is None:
                continue
            if "Received message on data channel" in msg and "sportmodestate" in msg:
                etat_local.append(tl)
            if tl > fin_locale + __import__("datetime").timedelta(seconds=12):
                break
    if len(etat_local) != len(imu):
        continue
    t_robot_debut = imu[0][0] + (t_local - etat_local[0]).total_seconds()
    t_robot_fin = imu[0][0] + (fin_locale - etat_local[0]).total_seconds()
    dy, n_y = debit_yaw(imu, t_robot_debut + 0.5, t_robot_fin)
    dl, n_l = debit_lineaire(imu, t_robot_debut + 0.5, t_robot_fin)
    # derive : 1,5 s apres la fin de la consigne.
    d_apres, _ = debit_yaw(imu, t_robot_fin, t_robot_fin + 1.5)
    print(
        f"{t_local.strftime('%H:%M:%S')}  {fin_locale.strftime('%H:%M:%S')}  "
        f"z={vz:+.2f}  yaw {dy if dy is None else round(dy, 1):>7} deg/s  "
        f"lin {dl if dl is None else round(dl, 3):>6} m/s   "
        f"{d_apres if d_apres is None else round(d_apres, 1):>7} deg/s"
    )
