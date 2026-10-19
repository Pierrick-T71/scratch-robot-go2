"""Programme GO2 Scratch : structure simple, sans variables ni expressions.

Pourquoi ce modèle est aussi maigre

L'enfant ne crée pas de variable et n'écrit pas de formule : toutes les
valeurs sont des CHOIX menus, résolus à la compilation. Il ne reste que deux
formes d'instruction : une action (« avancer pendant 2 secondes ») et une
structure (« répéter 3 fois », « si … alors »).

Le service reste seul juge

Ce modèle est une *demande*. Elle est validée intégralement ici, bornée, et
une condition n'est tranchée qu'au moment de l'exécution, avec l'état réel du
robot.

Distance ou durée ?

``SportClient.Move(vx, vy, vyaw)`` prend une VITESSE, jamais une distance.
Aucune commande « avancer de N cm » n'existe dans le SDK officiel lu. Les
déplacements sont donc exprimés en DURÉE.

Les rotations, elles, sont exprimées en DEGRÉS, parce que le cap (``yaw`` de
``SportModeState_``) est une donnée MESURÉE : « tourner de 90° » est
vérifiable, une distance ne l'est pas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .validation import CommandValidationError

#: Conditions réellement implémentées.
#:
#: ⚠️ `obstacle` en est volontairement ABSENT : aucune mesure de distance
#: n'a été identifiée dans le SDK officiel lu. Proposer ce bloc reviendrait à
#: afficher un nombre fabriqué.
CONDITIONS: dict[str, str] = {
    "posture_stand": "le robot est debout",
    "battery_low": "la batterie est faible",
}

#: En dessous de ce pourcentage, la batterie est considérée faible.
LOW_BATTERY_PERCENT = 30.0

#: Postures exposées, toutes vérifiées dans les exemples officiels lus.
POSTURES = frozenset({"stand", "sit", "balance"})

MOVE_DIRECTIONS = frozenset({"forward", "backward", "left", "right"})
TURN_DIRECTIONS = frozenset({"left", "right"})

#: Durées réellement proposées dans les menus de l'interface.
ALLOWED_SECONDS = frozenset({1.0, 2.0, 3.0, 5.0})
#: Angles réellement proposés dans les menus de l'interface.
ALLOWED_DEGREES = frozenset({45.0, 90.0, 180.0})
#: Nombres de répétitions réellement proposés.
ALLOWED_TIMES = frozenset({2, 3, 5, 10})

#: Profondeur maximale d'imbrication, protectrice de la pile.
MAX_NESTING = 64


def _number(value: Any, field_name: str) -> float:
    """Nombre fini. Les booléens sont explicitement refusés.

    `isinstance(True, int)` est vrai en Python : sans ce refus, `true`
    passerait pour 1.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CommandValidationError(f"Le champ « {field_name} » n’est pas un nombre.")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise CommandValidationError(f"Le champ « {field_name} » vaut un nombre impossible.")
    return number


def _line(raw: dict[str, Any]) -> int:
    line = raw.get("line", 0)
    return line if isinstance(line, int) and not isinstance(line, bool) else 0


# --------------------------------------------------------------------------
# Instructions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MoveStatement:
    direction: str
    seconds: float
    line: int = 0


@dataclass(frozen=True)
class TurnStatement:
    direction: str
    degrees: float
    line: int = 0


@dataclass(frozen=True)
class WaitStatement:
    seconds: float
    line: int = 0


@dataclass(frozen=True)
class PostureStatement:
    posture: str
    line: int = 0


@dataclass(frozen=True)
class StopMoveStatement:
    line: int = 0


@dataclass(frozen=True)
class StopProgramStatement:
    line: int = 0


@dataclass(frozen=True)
class RepeatStatement:
    times: int
    body: list["Statement"] = field(default_factory=list)
    line: int = 0


@dataclass(frozen=True)
class IfStatement:
    condition: str
    then: list["Statement"] = field(default_factory=list)
    otherwise: list["Statement"] | None = None
    line: int = 0


Statement = (
    MoveStatement
    | TurnStatement
    | WaitStatement
    | PostureStatement
    | StopMoveStatement
    | StopProgramStatement
    | RepeatStatement
    | IfStatement
)


@dataclass(frozen=True)
class Program:
    statements: list[Statement] = field(default_factory=list)


# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------


def _statements(raw: Any, depth: int) -> list[Statement]:
    if not isinstance(raw, list):
        raise CommandValidationError("Une suite d’instructions doit être une liste.")
    return [parse_statement(entry, depth + 1) for entry in raw]


def parse_statement(raw: Any, depth: int = 0) -> Statement:
    """Convertit une donnée reçue en instruction vérifiée."""
    if depth > MAX_NESTING:
        raise CommandValidationError("Le programme est trop imbriqué.")
    if not isinstance(raw, dict):
        raise CommandValidationError("Une instruction doit être un objet.")

    kind = raw.get("kind")
    line = _line(raw)

    if kind == "move":
        direction = raw.get("direction")
        if direction not in MOVE_DIRECTIONS:
            raise CommandValidationError(f"Le déplacement « {direction} » n’existe pas.")
        return MoveStatement(
            direction=direction, seconds=_number(raw.get("seconds"), "seconds"), line=line
        )
    if kind == "turn":
        direction = raw.get("direction")
        if direction not in TURN_DIRECTIONS:
            raise CommandValidationError(f"La rotation « {direction} » n’existe pas.")
        return TurnStatement(
            direction=direction, degrees=_number(raw.get("degrees"), "degrees"), line=line
        )
    if kind == "wait":
        return WaitStatement(seconds=_number(raw.get("seconds"), "seconds"), line=line)
    if kind == "posture":
        posture = raw.get("posture")
        if posture not in POSTURES:
            raise CommandValidationError(f"La posture « {posture} » n’existe pas.")
        return PostureStatement(posture=posture, line=line)
    if kind == "stop_move":
        return StopMoveStatement(line=line)
    if kind == "stop_program":
        return StopProgramStatement(line=line)
    if kind == "repeat":
        times = raw.get("times")
        if isinstance(times, bool) or not isinstance(times, int):
            raise CommandValidationError(
                "Un nombre de répétitions doit être un entier connu à la compilation."
            )
        if times < 0:
            raise CommandValidationError("Un nombre de répétitions ne peut pas être négatif.")
        return RepeatStatement(times=times, body=_statements(raw.get("body"), depth), line=line)
    if kind == "if":
        condition = raw.get("condition")
        if condition not in CONDITIONS:
            raise CommandValidationError(
                f"La condition « {condition} » n’existe pas. "
                "Aucune mesure correspondante n’a été identifiée dans le SDK officiel."
            )
        otherwise = raw.get("otherwise")
        return IfStatement(
            condition=condition,
            then=_statements(raw.get("then"), depth),
            otherwise=None if otherwise is None else _statements(otherwise, depth),
            line=line,
        )

    raise CommandValidationError(f"L’instruction « {kind} » n’existe pas.")


def parse_program(raw: Any) -> Program:
    """Convertit le `program` reçu du frontend en programme vérifié."""
    if not isinstance(raw, dict):
        raise CommandValidationError("Le programme doit être un objet.")
    # Un champ inconnu est refusé : une version de frontend plus récente ne
    # doit pas pouvoir introduire une instruction non vérifiée.
    unexpected = set(raw) - {"statements"}
    if unexpected:
        raise CommandValidationError(
            f"Le programme contient un champ inconnu : « {sorted(unexpected)[0]} »."
        )
    return Program(statements=_statements(raw.get("statements"), 0))


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


def count_steps(statements: list[Statement]) -> int:
    """Nombre d'instructions, répétitions développées."""
    total = 0
    for statement in statements:
        if isinstance(statement, RepeatStatement):
            total += max(1, statement.times) * max(1, count_steps(statement.body))
        elif isinstance(statement, IfStatement):
            total += 1 + count_steps(statement.then) + count_steps(statement.otherwise or [])
        else:
            total += 1
    return total


def max_seconds(statements: list[Statement]) -> float:
    """Durée maximale possible, en secondes.

    Pour une condition, c'est la branche « alors » : on ne peut pas savoir à
    l'avance laquelle sera prise, donc on retient la plus longue.
    """
    total = 0.0
    for statement in statements:
        match statement:
            case MoveStatement(_, seconds, _) | WaitStatement(seconds, _):
                total += seconds
            case TurnStatement(_, degrees, _):
                # Borne haute : l'angle est parcouru à la vitesse angulaire
                # maximale autorisée, 0,5 rad/s (~28,6 °/s).
                total += abs(degrees) / 28.6
            case RepeatStatement(times, body, _):
                total += times * max_seconds(body)
            case IfStatement(_, then, otherwise, _):
                # Pire cas : la plus LONGUE des deux branches. Prendre « alors »
                # par défaut refuserait à tort un programme dont le « sinon »
                # est le plus long — et le service peut bel et bien le prendre.
                total += max(max_seconds(then), max_seconds(otherwise or []))
            case _:
                pass
    return total


def conditions_used(statements: list[Statement]) -> set[str]:
    """Conditions présentes, pour vérification et documentation."""
    found: set[str] = set()
    for statement in statements:
        if isinstance(statement, IfStatement):
            found.add(statement.condition)
            found |= conditions_used(statement.then)
            found |= conditions_used(statement.otherwise or [])
        elif isinstance(statement, RepeatStatement):
            found |= conditions_used(statement.body)
    return found


@dataclass(frozen=True)
class StructureIssue:
    """Problème de structure, avec la ligne fautive pour localisation."""

    message: str
    line: int | None = None


@dataclass(frozen=True)
class StructureReport:
    valid: bool
    issues: list[StructureIssue]
    max_seconds: float
    steps: int

    def first_message(self) -> str:
        return self.issues[0].message if self.issues else ""


def validate_structure(program: Program, limits) -> StructureReport:
    """Validation AUTORITATIVE d'un programme.

    Vérifie ce qui est statique : durées, angles, imbrication, cumuls. Les
    conditions ne sont PAS évaluées ici : seul le service, avec l'état réel du
    robot, peut trancher.
    """
    issues: list[StructureIssue] = []
    statements = program.statements

    if not statements:
        issues.append(StructureIssue("Le programme ne contient aucune instruction."))

    def walk(items: list[Statement], depth: int) -> None:
        if depth > limits.program.max_nested_repeat_depth:
            issues.append(
                StructureIssue(
                    f"Les répétitions sont imbriquées trop profondément "
                    f"(maximum {limits.program.max_nested_repeat_depth})."
                )
            )
            return

        for statement in items:
            match statement:
                case MoveStatement(_, seconds, line):
                    if seconds not in ALLOWED_SECONDS:
                        issues.append(
                            StructureIssue(
                                f"Ce déplacement demande {seconds:g} s, "
                                "ce qui n’est pas proposé.",
                                line,
                            )
                        )
                    if not (
                        limits.timing.min_wait_seconds
                        <= seconds
                        <= limits.timing.max_wait_seconds
                    ):
                        issues.append(
                            StructureIssue(
                                f"Une durée doit être entre "
                                f"{limits.timing.min_wait_seconds:g} et "
                                f"{limits.timing.max_wait_seconds:g} secondes.",
                                line,
                            )
                        )

                case WaitStatement(seconds, line):
                    if seconds not in ALLOWED_SECONDS:
                        issues.append(
                            StructureIssue(
                                f"Cette attente demande {seconds:g} s, "
                                "ce qui n’est pas proposé.",
                                line,
                            )
                        )
                    if not (
                        limits.timing.min_wait_seconds
                        <= seconds
                        <= limits.timing.max_wait_seconds
                    ):
                        issues.append(
                            StructureIssue(
                                f"Une attente doit être entre "
                                f"{limits.timing.min_wait_seconds:g} et "
                                f"{limits.timing.max_wait_seconds:g} secondes.",
                                line,
                            )
                        )

                case TurnStatement(_, degrees, line):
                    if degrees not in ALLOWED_DEGREES:
                        issues.append(
                            StructureIssue(
                                f"Cette rotation demande {degrees:g}°, "
                                "ce qui n’est pas proposé.",
                                line,
                            )
                        )
                    if abs(degrees) > limits.motion.max_angle_per_step_deg:
                        issues.append(
                            StructureIssue(
                                f"Une rotation doit faire au plus "
                                f"{limits.motion.max_angle_per_step_deg:g}°.",
                                line,
                            )
                        )

                case RepeatStatement(times, body, line):
                    if times not in ALLOWED_TIMES:
                        issues.append(
                            StructureIssue(
                                f"Ce bloc répète {times} fois, ce qui n’est pas proposé.",
                                line,
                            )
                        )
                    if times > limits.program.max_repeat_count:
                        issues.append(
                            StructureIssue(
                                f"Ce bloc répète {times} fois, le maximum est "
                                f"{limits.program.max_repeat_count}.",
                                line,
                            )
                        )
                    walk(body, depth + 1)

                case IfStatement(condition, then, otherwise, line):
                    if condition not in CONDITIONS:
                        issues.append(
                            StructureIssue(
                                f"La condition « {condition} » n’existe pas.", line
                            )
                        )
                    walk(then, depth)
                    if otherwise is not None:
                        walk(otherwise, depth)

                case _:
                    pass

    walk(statements, 0)

    steps = count_steps(statements)
    if steps > limits.program.max_total_steps:
        issues.append(
            StructureIssue(
                f"Le programme contient {steps} instructions, "
                f"le maximum est {limits.program.max_total_steps}."
            )
        )

    worst = max_seconds(statements)
    if worst > limits.program.max_program_seconds:
        issues.append(
            StructureIssue(
                f"Le programme durerait au pire environ {worst:.0f} s, "
                f"le maximum est {limits.program.max_program_seconds:g} s."
            )
        )

    return StructureReport(
        valid=not issues, issues=issues, max_seconds=round(worst, 1), steps=steps
    )