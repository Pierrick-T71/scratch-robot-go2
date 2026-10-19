"""Test de bout en bout du branchement robot, via l'API du service."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def appel(methode: str, chemin: str, corps: dict | None = None) -> tuple[int, object]:
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(
        BASE + chemin,
        data=donnees,
        method=methode,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            return reponse.status, json.loads(reponse.read().decode())
    except urllib.error.HTTPError as erreur:
        return erreur.code, json.loads(erreur.read().decode())


def resume(etape: str) -> None:
    code, corps = appel("GET", "/api/status")
    if not isinstance(corps, dict):
        print(f"  {etape}: reponse inattendue (HTTP {code})")
        return
    position = corps.get("position") or {}
    print(
        f"  {etape}: mode={corps.get('mode')} "
        f"connecte={corps.get('connected')} "
        f"bloque={corps.get('blockedReason')} "
        f"x={position.get('x')} y={position.get('y')} "
        f"cap={corps.get('yawRad')} "
        f"batterie={corps.get('batteryPercent')}"
    )


def brancher(test: bool) -> None:
    code, corps = appel(
        "POST",
        "/api/robot/connect",
        {
            "robot_ip": "172.16.8.11",
            "network_interface": "webrtc",
            "lancer_test": test,
        },
    )
    print(f"  HTTP {code} : {json.dumps(corps, ensure_ascii=False)}")


print("=== 1. branchement (sans mouvement) ===")
brancher(False)
resume("etat")

print()
print("=== 2. deuxieme branchement (l'ancien canal doit etre relache) ===")
brancher(False)
resume("etat")

print()
print("=== 3. branchement avec test physique : le robot s'assoit ===")
brancher(True)
resume("etat")
