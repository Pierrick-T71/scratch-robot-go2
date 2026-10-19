"""Interpréteur : développe répétitions et conditions, sans variables.

Aucune expression n'est évaluée ici. Les valeurs sont déjà résolues — ce sont
des CHOIX menus — et les conditions se tranchent avec l'état réel du robot.

## La condition n'est pas devinée

« Si la batterie est faible » se décide au moment de l'exécution, avec la
batterie que le service a LUE. Si cette mesure est absente, le programme
s'arrête et le signale : il ne suppose pas « batterie correcte », car cela
ferait passer une condition à faux sans que personne ne s'en aperçoive.

## Le mouvement est TOUJOURS borné

Même une valeur déjà validée est re-bornée ici. Un service qui tournerait avec
un `limits` plus permissif que celui de la validation ne doit pas pouvoir
publier une vitesse hors des limites du fichier partagé.
"""

from __future__ import annotations

from dataclasses import dataclass

from .program import (
    IfStatement,
    MoveStatement,
    PostureStatement,
    Program,
    RepeatStatement,
    StopMoveStatement,
    StopProgramStatement,
    Statement,
    TurnStatement,
    WaitStatement,
)
from .validation import CommandKind, RobotCommand


class ProgramError(RuntimeError):
    """Le programme ne peut pas être exécuté.

    Levée AVANT tout mouvement : le service interrompt l'exécution et
    signale, sans avoir commandé quoi que ce soit.
    """


class StopProgram(Exception):
    """Levée par « Arrêter le programme ». Interrompt la boucle."""


@dataclass
class RobotTruth:
    """Ce que le service sait RÉELLEMENT de l'instant présent.

    Un champ à `None` signifie « pas mesuré ». On ne le remplace jamais par
    0 : 0 est une valeur plausible, et la faire passer pour une mesure
    ferait basculer une condition sans que l'enfant l'apprenne.
    """

    posture: str | None = None
    battery_percent: float | None = None

    def condition(self, name: str, limits) -> bool:
        from .program import LOW_BATTERY_PERCENT

        if name == "posture_stand":
            if self.posture is None:
                raise ProgramError(
                    "Le service ne sait pas si le robot est debout. "
                    "Aucun chiffre n’est inventé pour décider."
                )
            return self.posture == "stand"
        if name == "battery_low":
            if self.battery_percent is None:
                raise ProgramError(
                    "La batterie n’a pas été mesurée. "
                    "Aucun chiffre n’est inventé pour décider."
                )
            return self.battery_percent < LOW_BATTERY_PERCENT
        raise ProgramError(f"La condition « {name} » n’est pas prévue.")


class Interpreter:
    """Développe répétitions et conditions en instructions physiques."""

    def __init__(self, limits, truth: RobotTruth) -> None:
        self._limits = limits
        self._truth = truth

    # -- Instructions -------------------------------------------------------

    def run(self, program: Program) -> list[RobotCommand]:
        """Produit la suite d'instructions physiques à exécuter.

        ⚠️ Une condition est tranchée ICI, avec l'état du moment. Le résultat
        est figé juste avant l'exécution ; entre la décision et la fin du
        programme, la batterie peut baisser. C'est le comportement de tout
        système conditionnel réel, et l'enjeu ici est qu'aucune valeur ne soit
        INVENTÉE pour éviter ce décalage.
        """
        out: list[RobotCommand] = []
        try:
            self._block(program.statements, out, depth=0)
        except StopProgram:
            # ⚠️ On garde ce qui a DÉJÀ été calculé.
            #
            # Lever ici sans rien retourner ferait perdre les mouvements
            # précédant « Arrêter le programme » : le robot resterait immobile
            # alors que le programme les demandait. « Arrêter » signifie
            # « ne PAS continuer », jamais « oublier ce qui précède ».
            pass
        return out

    def _block(
        self, statements: list[Statement], out: list[RobotCommand], depth: int
    ) -> None:
        limits = self._limits
        if depth > limits.program.max_nested_repeat_depth:
            raise ProgramError("Les répétitions sont trop imbriquées.")

        for statement in statements:
            if len(out) > limits.program.max_total_steps:
                raise ProgramError("Le programme est trop long.")

            match statement:
                case RepeatStatement(times, body, _):
                    for _ in range(min(times, limits.program.max_repeat_count)):
                        self._block(body, out, depth + 1)
                case IfStatement(condition, then, otherwise, _):
                    branch = then if self._truth.condition(condition, self._limits) else (otherwise or [])
                    self._block(branch, out, depth + 1)
                case StopProgramStatement():
                    raise StopProgram()
                case _:
                    command = self.lower(statement)
                    if command is not None:
                        out.append(command)

    def lower(self, statement: Statement) -> RobotCommand | None:
        """Traduit une instruction en commande exécutable.

        Retourne `None` pour ce qui ne pilote aucun organe (seule
        « Arrêter le robot », qui est elle aussi traduite, et les
        instructions de structure traitées plus haut).
        """
        limits = self._limits

        match statement:
            case MoveStatement(direction, seconds, _):
                kind = {
                    "forward": CommandKind.MOVE_FORWARD,
                    "backward": CommandKind.MOVE_BACKWARD,
                    "left": CommandKind.MOVE_LEFT,
                    "right": CommandKind.MOVE_RIGHT,
                }[direction]
                return RobotCommand(
                    kind=kind,
                    # La vitesse est CHOISIE PAR LE SERVICE, pas par l'enfant :
                    # un paramètre de moins, et une limite de sécurité qui ne
                    # peut pas être dépassée par une saisie.
                    speed=limits.motion.max_linear_speed,
                    duration_s=self._clamp_duration(seconds),
                )

            case TurnStatement(direction, degrees, _):
                return RobotCommand(
                    kind=(
                        CommandKind.TURN_LEFT
                        if direction == "left"
                        else CommandKind.TURN_RIGHT
                    ),
                    speed=limits.motion.max_angular_speed,
                    duration_s=self._angle_duration(degrees),
                    # L'angle demandé sert de cible MESURÉE : l'adaptateur
                    # s'arrête quand le cap est atteint, pas au bout d'un temps.
                    angle_deg=abs(degrees),
                )

            case WaitStatement(seconds, _):
                return RobotCommand(
                    kind=CommandKind.WAIT, duration_s=self._clamp_duration(seconds)
                )

            case PostureStatement(posture, _):
                kind = {
                    "stand": CommandKind.STAND_UP,
                    "sit": CommandKind.SIT_DOWN,
                    "balance": CommandKind.BALANCE,
                }[posture]
                return RobotCommand(kind=kind)

            case StopMoveStatement():
                return RobotCommand(kind=CommandKind.STOP)

            case _:
                raise ProgramError(f"L’instruction « {statement} » n’est pas prévue.")

    def _clamp_duration(self, seconds: float) -> float:
        limits = self._limits
        value = abs(seconds)
        if value < limits.timing.min_wait_seconds:
            return limits.timing.min_wait_seconds
        if value > limits.timing.max_wait_seconds:
            return limits.timing.max_wait_seconds
        return value

    def _angle_duration(self, degrees: float) -> float:
        """Durée nécessaire pour parcourir un angle, à vitesse maximale.

        Sert de BORNURE SUPÉRIEURE, jamais de promesse : l'arrêt réel est
        déclenché par la mesure du cap, et ce délai est ce après quoi on
        renonce à atteindre la cible.
        """
        limits = self._limits
        import math

        seconds = math.radians(abs(degrees)) / limits.motion.max_angular_speed
        return self._clamp_duration(seconds)