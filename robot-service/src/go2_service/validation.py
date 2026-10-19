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
    """Capacités réellement exposées aux enfants.

    Les quatre premières pilotent le robot. Les suivantes distinguent ce que
    le SDK confirme de ce qu'il ne confirme pas :

    - ``VARIABLE`` et ``BROADCAST`` ne touchent aucun organe : la logique du
      programme s'exécute dans le service, toujours disponible.
    - ``SENSOR_STATE`` lit ``SportModeState_`` (sujet ``rt/sportmodestate``),
      lu dans les exemples officiels.
    - ``SENSOR_OBSTACLE`` n'est PAS confirmée : le simulateur la propose,
      l'adaptateur physique ne la revendique pas. C'est ce qui empêche un
      bloc capteur de mentir sur un robot réel.
    """

    MOVEMENT = "movement"
    POSTURE = "posture"
    WAIT = "wait"
    STOP = "stop"
    VARIABLE = "variable"
    BROADCAST = "broadcast"
    SENSOR_STATE = "sensor_state"
    SENSOR_OBSTACLE = "sensor_obstacle"


#: Capacités dont la logique s'exécute dans le service, robot réel compris.
ALWAYS_AVAILABLE: frozenset[Capability] = frozenset(
    {Capability.MOVEMENT, Capability.POSTURE, Capability.WAIT, Capability.STOP,
     Capability.VARIABLE, Capability.BROADCAST}
)


class CommandKind(str, Enum):
    """Instructions PHYSIQUES : celles qui atteignent le robot.

    Les instructions purement logiques (variables, conditions, messages) ne
    sont PAS des commandes : elles sont interprétées par le moteur
    d'exécution et ne touchent aucun organe.
    """

    MOVE_FORWARD = "move_forward"
    MOVE_BACKWARD = "move_backward"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    WAIT = "wait"
    STAND_UP = "stand_up"
    SIT_DOWN = "sit_down"
    LIE_DOWN = "lie_down"
    BALANCE = "balance"
    STOP = "stop"


_CAPABILITY_BY_KIND: dict[CommandKind, Capability] = {
    CommandKind.MOVE_FORWARD: Capability.MOVEMENT,
    CommandKind.MOVE_BACKWARD: Capability.MOVEMENT,
    CommandKind.MOVE_LEFT: Capability.MOVEMENT,
    CommandKind.MOVE_RIGHT: Capability.MOVEMENT,
    CommandKind.TURN_LEFT: Capability.MOVEMENT,
    CommandKind.TURN_RIGHT: Capability.MOVEMENT,
    CommandKind.WAIT: Capability.WAIT,
    CommandKind.STAND_UP: Capability.POSTURE,
    CommandKind.SIT_DOWN: Capability.POSTURE,
    CommandKind.LIE_DOWN: Capability.POSTURE,
    CommandKind.BALANCE: Capability.POSTURE,
    CommandKind.STOP: Capability.STOP,
}

#: Translations : `Move(vx, vy, vyaw)` prend des VITESSES, pas des distances.
#: Le SDK Go2 n'expose aucune commande « avancer de N cm ».
_MOVE_KINDS = frozenset(
    {CommandKind.MOVE_FORWARD, CommandKind.MOVE_BACKWARD,
     CommandKind.MOVE_LEFT, CommandKind.MOVE_RIGHT}
)
_TURN_KINDS = frozenset({CommandKind.TURN_LEFT, CommandKind.TURN_RIGHT})
#: Postures NON vérifiées dans les exemples officiels unitree_sdk2 lus.
UNVERIFIED_POSTURES = frozenset({CommandKind.LIE_DOWN})


@dataclass(frozen=True)
class RobotCommand:
    """Une instruction physique validée, prête à être exécutée.

    ⚠️ Les déplacements portent une VITESSE et une DURÉE, jamais une distance.
    `SportClient.Move(vx, vy, vyaw)` fixe une consigne de vitesse ; aucune
    commande « avancer de N cm » n'existe dans le SDK lu. Exiger une distance
    nous ferait convertir en vitesse en inventant une unité de commande.

    Les champs non pertinents restent à 0. La construction passe
    exclusivement par `parse_command`, qui refuse tout objet non conforme.
    """

    kind: CommandKind
    #: Vitesse demandée, en m/s (translation) ou rad/s (rotation).
    speed: float = 0.0
    #: Durée demandée, en secondes.
    duration_s: float = 0.0
    #: Angle demandé pour une rotation, en degrés.
    #:
    #: Ce n'est PAS une durée : c'est la CIBLE MESURÉE. Le cap (`yaw`) est une
    #: donnée réelle de `SportModeState_`, donc « tourner de 90° » est
    #: vérifiable — contrairement à une distance, qui ne l'est pas.
    angle_deg: float = 0.0

    @property
    def capability(self) -> Capability:
        return _CAPABILITY_BY_KIND[self.kind]

    @property
    def is_motion(self) -> bool:
        return self.kind in _MOVE_KINDS or self.kind in _TURN_KINDS

    @property
    def is_rotation(self) -> bool:
        return self.kind in _TURN_KINDS

    @property
    def verified_for_real_mode(self) -> bool:
        """`False` si l'action n'a pas été confirmée dans le SDK lu."""
        return self.kind not in UNVERIFIED_POSTURES

    def label(self) -> str:
        """Description courte, en français, utilisée par l'interface."""
        match self.kind:
            case CommandKind.MOVE_FORWARD:
                return f"Avancer à {self.speed:g} m/s pendant {self.duration_s:g} s"
            case CommandKind.MOVE_BACKWARD:
                return f"Reculer à {self.speed:g} m/s pendant {self.duration_s:g} s"
            case CommandKind.MOVE_LEFT:
                return f"Aller à gauche à {self.speed:g} m/s pendant {self.duration_s:g} s"
            case CommandKind.MOVE_RIGHT:
                return f"Aller à droite à {self.speed:g} m/s pendant {self.duration_s:g} s"
            case CommandKind.TURN_LEFT:
                return f"Tourner à gauche pendant {self.duration_s:g} s"
            case CommandKind.TURN_RIGHT:
                return f"Tourner à droite pendant {self.duration_s:g} s"
            case CommandKind.WAIT:
                return f"Attendre {self.duration_s:g} s"
            case CommandKind.STAND_UP:
                return "Se mettre debout"
            case CommandKind.SIT_DOWN:
                return "S’asseoir"
            case CommandKind.LIE_DOWN:
                return "Se coucher (simulation seulement)"
            case CommandKind.BALANCE:
                return "Se stabiliser debout"
            case CommandKind.STOP:
                return "Arrêter le déplacement"
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

    if kind in _MOVE_KINDS or kind in _TURN_KINDS or kind is CommandKind.WAIT:
        speed = 0.0
        if kind in _MOVE_KINDS:
            speed = abs(_as_finite_number(raw.get("speed"), "speed", kind))
        angle = 0.0
        if kind in _TURN_KINDS:
            # Cible MESURÉE : le cap est une donnée réelle de `SportModeState_`.
            # Sans elle, la rotation ne serait qu'une durée sans garantie.
            raw_angle = raw.get("angleDeg")
            if raw_angle is not None:
                angle = abs(_as_finite_number(raw_angle, "angleDeg", kind))
        return RobotCommand(
            kind=kind,
            speed=speed,
            duration_s=abs(_as_finite_number(raw.get("durationS"), "durationS", kind)),
            angle_deg=angle,
        )
    return RobotCommand(kind=kind)


def parse_program(raw: Any) -> list[RobotCommand]:
    """Convertit une liste plate d'instructions physiques.

    ⚠️ Cette forme est celle d'un programme DÉJÀ résolu : toutes les
    conditions y ont été tranchées. Un programme contenant des conditions
    doit passer par `go2_service.program`, qui les préserve.
    """
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
    #: Vitesse maximale demandée, m/s (rad/s pour une rotation).
    max_speed_mps: float

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
    max_speed = 0.0

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

        # Une action non vérifiée dans le SDK ne doit jamais être exécutée sur
        # un robot réel, même si un client falsifié la demande.
        if not command.verified_for_real_mode and Capability.POSTURE in available:
            issues.append(
                ValidationIssue(
                    f"« {command.label()} » n’est pas vérifié sur le robot : "
                    "cette action est réservée à la simulation.",
                    index,
                )
            )

        match command.kind:
            case _ if command.kind in _MOVE_KINDS:
                speed = command.speed
                if not (0.0 <= speed <= limits.motion.max_linear_speed):
                    issues.append(
                        ValidationIssue(
                            f"Une vitesse doit être entre 0 et "
                            f"{limits.motion.max_linear_speed:g} m/s "
                            f"(reçu {speed:g} m/s).",
                            index,
                        )
                    )
                max_speed = max(max_speed, speed)

            case _ if command.kind in _TURN_KINDS:
                # La rotation est cadencée par la borne angulaire.
                max_speed = max(max_speed, limits.motion.max_angular_speed)

            case _:
                pass

        # La durée est bornée pour TOUTE instruction temporelle.
        if command.is_motion or command.kind is CommandKind.WAIT:
            if not (
                limits.timing.min_wait_seconds
                <= command.duration_s
                <= limits.timing.max_wait_seconds
            ):
                issues.append(
                    ValidationIssue(
                        f"Une durée doit être entre "
                        f"{limits.timing.min_wait_seconds:g} et "
                        f"{limits.timing.max_wait_seconds:g} secondes "
                        f"(reçu {command.duration_s:g} s).",
                        index,
                    )
                )
            estimated += command.duration_s
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
        max_speed_mps=round(max_speed, 3),
    )