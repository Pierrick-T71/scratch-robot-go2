"""Planification de mouvement : distance/angle -> vitesse + durée.

FAIT VÉRIFIÉ SUR LE SDK OFFICIEL (unitree_sdk2, exemple `go2_sport_client`) :
`SportClient.Move(vx, vy, vyaw)` prend une VITESSE. Le SDK n'expose aucune
commande « avancer de N cm » ni « tourner de N degrés ».

Il faut donc reconstruire la distance nous-mêmes. Ce module fait la
conversion et fournit les délais de sécurité. Il ne prétend PAS que le
déplacement est arrivé : cette affirmation exige l'état mesuré, produit par
l'adaptateur.
"""

from __future__ import annotations

import math

from ..config import Limits
from ..validation import CommandKind, RobotCommand
from .base import AdapterError, MotionPlan

#: Durée minimale d'une commande de mouvement (évite la division par zéro).
MIN_MOVE_DURATION_S = 0.05

#: Marge entre la durée nominale et le délai de déclenchement de l'arrêt.
#: Un robot qui glisse ou bute doit s'arrêter, pas continuer à forcer.
MOVE_TIMEOUT_MARGIN = 2.5

#: Tolerance de fin de déplacement, en centimètres.
POSITION_TOLERANCE_CM = 5.0

#: Tolérance de fin de rotation, en degrés.
YAW_TOLERANCE_DEG = 8.0

_DEG_PER_RAD = 180.0 / math.pi


def nominal_duration_for_distance(distance_cm: float, speed_mps: float) -> float:
    """Durée qu'il FAUDRAIT pour parcourir la distance à cette vitesse.

    C'est une estimation de commande, pas une garantie d'exécution.
    """
    return max(MIN_MOVE_DURATION_S, (abs(distance_cm) / 100.0) / speed_mps)


def nominal_duration_for_angle(angle_deg: float, speed_rps: float) -> float:
    """Durée qu'il faudrait pour effectuer la rotation à cette vitesse."""
    return max(MIN_MOVE_DURATION_S, math.radians(abs(angle_deg)) / speed_rps)


def timeout_for(nominal_s: float) -> float:
    """Délai au-delà duquel l'arrêt de sécurité se déclenche."""
    return nominal_s * MOVE_TIMEOUT_MARGIN + 1.0


def plan_command(command: RobotCommand, limits: Limits) -> MotionPlan | None:
    """Traduit une instruction en plan de mouvement.

    ⚠️ Le programme fournit DÉJÀ une vitesse et une durée. Ce module ne
    convertit plus une distance en vitesse : il borne, et calcule le délai
    d'arrêt de sécurité.

    Retourne `None` pour les instructions qui ne sont pas des déplacements
    (posture, arrêt, attente) : elles ne passent pas par la boucle de vitesse.
    """
    if command.kind in (CommandKind.MOVE_LEFT, CommandKind.MOVE_RIGHT):
        lateral = command.speed if command.kind is CommandKind.MOVE_LEFT else -command.speed
        plan = MotionPlan(
            linear_speed_mps=0.0,
            lateral_speed_mps=lateral,
            angular_speed_rps=0.0,
            nominal_duration_s=command.duration_s,
            timeout_s=timeout_for(command.duration_s),
        )
        assert_speed_within_limits(plan, limits)
        return plan

    if command.kind in (CommandKind.MOVE_FORWARD, CommandKind.MOVE_BACKWARD):
        linear = command.speed
        if command.kind is CommandKind.MOVE_BACKWARD:
            linear = -linear
        plan = MotionPlan(
            linear_speed_mps=linear,
            angular_speed_rps=0.0,
            nominal_duration_s=command.duration_s,
            timeout_s=timeout_for(command.duration_s),
            distance_cm=abs(linear) * command.duration_s * 100.0,
        )
        assert_speed_within_limits(plan, limits)
        return plan

    if command.kind in (CommandKind.TURN_LEFT, CommandKind.TURN_RIGHT):
        sign = 1.0 if command.kind is CommandKind.TURN_LEFT else -1.0
        nominal = command.duration_s
        # La CIBLE est l'angle demandé, pas une reconstruction depuis la durée.
        # Le cap est mesuré : c'est lui qui arrête le rotation. La durée ne
        # sert qu'à borner le temps d'attente si la mesure n'arrive jamais.
        target = command.angle_deg or math.degrees(limits.motion.max_angular_speed * nominal)
        plan = MotionPlan(
            linear_speed_mps=0.0,
            angular_speed_rps=sign * limits.motion.max_angular_speed,
            nominal_duration_s=nominal,
            timeout_s=timeout_for(nominal),
            angle_deg=abs(target),
        )
        assert_speed_within_limits(plan, limits)
        return plan

    return None


def travelled_distance_cm(
    start_xy: tuple[float, float], end_xy: tuple[float, float]
) -> float:
    """Distance rectiligne parcourue entre deux points, en centimètres.

    Le SDK ne fournit PAS d'odométrie : `SportModeState.position()` est une
    position estimée par le contrôleur, à ne pas traiter comme une mesure
    absolue. Cette valeur sert à décider « assez proche », pas à certifier
    une distance.
    """
    dx = end_xy[0] - start_xy[0]
    dy = end_xy[1] - start_xy[1]
    return math.hypot(dx, dy) * 100.0


def shortest_angular_difference_deg(a_rad: float, b_rad: float) -> float:
    """Écart angulaire le plus court entre deux caps, en degrés.

    Indispensable pour tourner : sans cela, un passage de 179° à -179°
    donnerait un écart de 358° au lieu de 2°.
    """
    delta = (b_rad - a_rad + math.pi) % (2.0 * math.pi) - math.pi
    return abs(math.degrees(delta))


def assert_speed_within_limits(plan: MotionPlan, limits: Limits) -> None:
    """Garde-fou : aucune vitesse publiée ne doit dépasser les limites.

    Appelée par chaque adaptateur AVANT de publier une consigne. C'est une
    protection de dernier niveau, indépendante de la validation du programme.

    ⚠️ Le canal LATÉRAL (`vy`) est vérifié contre la borne LINÉAIRE, et non
    angulaire. Oublier ce canal laisserait passer `Move(0, 3.0, 0)` sur un
    robot limité à 0,3 m/s — un écart d'un facteur dix, invisible de loin.
    """
    if abs(plan.linear_speed_mps) > limits.motion.max_linear_speed + 1e-9:
        raise AdapterError(
            "Vitesse linéaire refusée : elle dépasse la limite autorisée.",
        )
    if abs(plan.lateral_speed_mps) > limits.motion.max_linear_speed + 1e-9:
        raise AdapterError(
            "Vitesse latérale refusée : elle dépasse la limite autorisée.",
        )
    if abs(plan.angular_speed_rps) > limits.motion.max_angular_speed + 1e-9:
        raise AdapterError(
            "Vitesse angulaire refusée : elle dépasse la limite autorisée.",
        )