"""Modèle de commandes interne et validation autoritaire.

Point important : ce sont des commandes du PROJET, pas des méthodes du SDK
Unitree. Le service est le seul à traduire vers l'API réelle du robot.

La validationliving ici est la seule opposable : celle du frontend n'est
qu'un confort d'affichage. Un client modifié reçoit exactement le même refus.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from .config import Limits


class Capability(str, Enum):
    """Les quatre capacités réellement exposées aux enfants."""

    MOVEMENT = "movement"
    POSTURE = "posture"
    WAIT = "wait"
    STOP = "stop"


class CommandKind(str, Enum):
    MOVE_FORWARD = "move_forward"
    MOVE_BACKWARD = "move_backward"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    WAIT = "wait"
    STAND_UP = "stand_up"
    SIT_DOWN = "sit_down"
    STOP = "stop"


_CAPABILITY_BY_KIND: dict[CommandKind, Capability] = {
    CommandKind.MOVE_FORWARD: Capability.MOVEMENT,
    CommandKind.MOVE_BACKWARD: Capability.MOVEMENT,
    CommandKind.TURN_LEFT: Capability.MOVEMENT,
    CommandKind.TURN_RIGHT: Capability.MOVEMENT,
    CommandKind.WAIT: Capability.WAIT,
    CommandKind.STAND_UP: Capability.POSTURE,
    CommandKind.SIT_DOWN: Capability.POSTURE,
    CommandKind.STOP: Capability.STOP,
}

_DISTANCE_KINDS = {CommandKind.MOVE_FORWARD, CommandKind.MOVE_BACKWARD}
_ANGLE_KINDS = {CommandKind.TURN_LEFT, CommandKind.TURN_RIGHT}


@dataclass(frozen=True)
class RobotCommand:
    """Une instruction validée et prête à être exécutée.

    Les champs non pertinents restent à 0. La construction passe
    exclusivement par `parse_command`, qui refuse tout objet non conforme.
    """

    kind: CommandKind
    distance_cm: float = 0.0
    angle_deg: float = 0.0
    seconds: float = 0.0

    @property
    def capability(self) -> Capability:
        return _CAPABILITY_BY_KIND[self.kind]

    @property
    def is_motion(self) -> bool:
        return self.kind in _DISTANCE_KINDS or self.kind in _ANGLE_KINDS

    def label(self) -> str:
        """Description courte, en français, utilisée par l'interface."""
        match self.kind:
            case CommandKind.MOVE_FORWARD:
                return f"Avancer de {self.distance_cm:g} cm"
            case CommandKind.MOVE_BACKWARD:
                return f"Reculer de {self.distance_cm:g} cm"
            case CommandKind.TURN_LEFT:
                return f"Tourner à gauche de {self.angle_deg:g}°"
            case CommandKind.TURN_RIGHT:
                return f"Tourner à droite de {self.angle_deg:g}°"
            case CommandKind.WAIT:
                return f"Attendre {self.seconds:g} s"
            case CommandKind.STAND_UP:
                return "Se mettre debout"
            case CommandKind.SIT_DOWN:
                return "S’asseoir"
            case CommandKind.STOP:
                return "S’arrêter"
        return self.kind.value


class CommandValidationError(ValueError):
    """Une instruction est refusée. Le message est destiné à l'enfant."""


def _as_finite_number(value: Any, field: str, kind: CommandKind) -> float:
    """Extrait un nombre fini. Les booléens sont explicitement refusés."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CommandValidationError(
            f"L’instruction « {kind.value} » a un champ « {field} » qui n’est pas un nombre."
        )
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise CommandValidationError(
            f"L’instruction « {kind.value} » a un nombre impossible."
        )
    return number


def parse_command(raw: Any) -> RobotCommand:
    """Convertit une donnée reçue du réseau en `RobotCommand` vérifiée.

    Toute forme inattendue est refusée : aucune confiance n'est accordée à
    l'entrée.
    """
    if not isinstance(raw, dict):
        raise CommandValidationError("Une instruction doit être un objet.")

    kind_value = raw.get("kind")
    if not isinstance(kind_value, str):
        raise CommandValidationError("Il manque le type d’une instruction.")

    try:
        kind = CommandKind(kind_value)
    except ValueError as exc:
        raise CommandValidationError(
            f"L’instruction « {kind_value} » n’existe pas."
        ) from exc

    if kind in _DISTANCE_KINDS:
        return RobotCommand(
            kind=kind,
            distance_cm=abs(_as_finite_number(raw.get("distanceCm"), "distanceCm", kind)),
        )
    if kind in _ANGLE_KINDS:
        return RobotCommand(
            kind=kind,
            angle_deg=abs(_as_finite_number(raw.get("angleDeg"), "angleDeg", kind)),
        )
    if kind is CommandKind.WAIT:
        return RobotCommand(
            kind=kind,
            seconds=_as_finite_number(raw.get("seconds"), "seconds", kind),
        )
    return RobotCommand(kind=kind)


def parse_program(raw: Any) -> list[RobotCommand]:
    """Convertit la liste d'instructions d'un programme."""
    if not isinstance(raw, list):
        raise CommandValidationError("Le programme doit être une liste d’instructions.")
    return [parse_command(entry) for entry in raw]


@dataclass(frozen=True)
class ValidationIssue:
    """Un problème détaillé, avec sa position pour le localisation."""

    message: str
    index: int | None = None


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    issues: list[ValidationIssue]
    estimated_seconds: float
    total_distance_cm: float
    total_angle_deg: float

    def first_message(self) -> str:
        return self.issues[0].message if self.issues else ""


def validate_program(
    commands: list[RobotCommand],
    limits: Limits,
    available: frozenset[Capability],
) -> ValidationReport:
    """Valide entièrement un programme. Fonction autoritaire.

    Vérifie : plages par instruction, cumuls globaux, nombre d'étapes,
    durée estimée, et disponibilité de chaque capacité utilisée.
    """
    issues: list[ValidationIssue] = []

    if not commands:
        issues.append(
            ValidationIssue("Le programme ne contient aucune instruction.")
        )

    if len(commands) > limits.program.max_total_steps:
        issues.append(
            ValidationIssue(
                f"Le programme contient {len(commands)} instructions, "
                f"le maximum est {limits.program.max_total_steps}."
            )
        )

    estimated = 0.0
    total_distance = 0.0
    total_angle = 0.0

    for index, command in enumerate(commands):
        # Capacité disponible ?
        if command.capability not in available:
            issues.append(
                ValidationIssue(
                    f"L’action « {command.label()} » n’est pas disponible "
                    "avec la configuration actuelle.",
                    index,
                )
            )

        match command.kind:
            case k if k in _DISTANCE_KINDS:
                d = command.distance_cm
                if not (
                    limits.motion.min_distance_per_step_cm
                    <= d
                    <= limits.motion.max_distance_per_step_cm
                ):
                    issues.append(
                        ValidationIssue(
                            f"Un déplacement doit faire entre "
                            f"{limits.motion.min_distance_per_step_cm:g} et "
                            f"{limits.motion.max_distance_per_step_cm:g} cm "
                            f"(reçu {d:g} cm).",
                            index,
                        )
                    )
                total_distance += d
                # Estimation de durée à la vitesse maximale autorisée.
                estimated += (d / 100.0) / limits.motion.max_linear_speed

            case k if k in _ANGLE_KINDS:
                a = command.angle_deg
                if not (
                    limits.motion.min_angle_per_step_deg
                    <= a
                    <= limits.motion.max_angle_per_step_deg
                ):
                    issues.append(
                        ValidationIssue(
                            f"Une rotation doit faire entre "
                            f"{limits.motion.min_angle_per_step_deg:g} et "
                            f"{limits.motion.max_angle_per_step_deg:g} degrés "
                            f"(reçu {a:g}°).",
                            index,
                        )
                    )
                total_angle += a
                import math

                estimated += math.radians(a) / limits.motion.max_angular_speed

            case CommandKind.WAIT:
                s = command.seconds
                if not (limits.timing.min_wait_seconds <= s <= limits.timing.max_wait_seconds):
                    issues.append(
                        ValidationIssue(
                            f"Une attente doit faire entre "
                            f"{limits.timing.min_wait_seconds:g} et "
                            f"{limits.timing.max_wait_seconds:g} secondes "
                            f"(reçu {s:g} s).",
                            index,
                        )
                    )
                estimated += max(0.0, s)

            case _:
                pass

    if total_distance > limits.program.max_total_distance_cm:
        issues.append(
            ValidationIssue(
                f"Le programme demande {total_distance:g} cm de déplacement, "
                f"le maximum est {limits.program.max_total_distance_cm:g} cm."
            )
        )

    if total_angle > limits.program.max_total_angle_deg:
        issues.append(
            ValidationIssue(
                f"Le programme demande {total_angle:g}° de rotation, "
                f"le maximum est {limits.program.max_total_angle_deg:g}°."
            )
        )

    if estimated > limits.program.max_program_seconds:
        issues.append(
            ValidationIssue(
                f"Le programme durerait environ {estimated:.0f} s, "
                f"le maximum est {limits.program.max_program_seconds:g} s."
            )
        )

    return ValidationReport(
        valid=not issues,
        issues=issues,
        estimated_seconds=round(estimated, 1),
        total_distance_cm=total_distance,
        total_angle_deg=total_angle,
    )