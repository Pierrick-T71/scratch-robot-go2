"""Moteur d'exécution des programmes.

Rôles :
  - interpréter le programme (répétitions, conditions) ;
  - exécuter les instructions physiques une par une, dans l'ordre ;
  - propager l'arrêt demandé à l'instruction en cours ;
  - interdire toute exécution concurrente ;
  - ne jamais déclarer un déplacement « réussi » sans mesure.

Le moteur ne connaît que le contrat `RobotAdapter` : aucune notion de SDK.

## Conditions et état du robot

Les conditions se tranchent au moment de l'exécution, avec l'état réellement
lu par l'adaptateur. Si une mesure manque, l'exécution s'arrête et le signale
plutôt que de supposer une valeur favorable.

## L'arrêt est garanti

`_finalize` demande toujours l'arrêt à l'adaptateur, y compris après une
exception : aucune consigne de mouvement ne survit à la fin du programme.
"""

from __future__ import annotations

import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from .adapters.base import AdapterError, CommandOutcome, RobotAdapter, SafetyInterrupt, StopSignal
from .interpreter import Interpreter, ProgramError, RobotTruth
from .obstacles import (
    direction_of,
    obstacle_message,
    required_clearance_m,
    travel_distance_m,
)
from .validation import RobotCommand

log = logging.getLogger(__name__)

#: Raisons de fin d'exécution, exposées telles quelles à l'interface.
FinishReason = str

FINISH_COMPLETED: FinishReason = "completed"
FINISH_STOPPED: FinishReason = "stopped"
FINISH_ERROR: FinishReason = "error"
FINISH_SAFETY: FinishReason = "safety"


@dataclass
class ExecutionEvent:
    """Événement d'exécution, relayé au frontend par WebSocket."""

    type: str
    index: int | None = None
    label: str | None = None
    outcome: str | None = None
    measured: dict[str, float] | None = None
    reason: FinishReason | None = None
    message: str | None = None


@dataclass
class ActiveExecution:
    """Exécution en cours, gardée pour permettre l'arrêt à distance."""

    run_id: str
    stop_signal: StopSignal = field(default_factory=StopSignal)
    #: Dernier battement reçu du frontend (monotonic).
    last_heartbeat: float = field(default_factory=time.monotonic)
    started_at: float = field(default_factory=time.monotonic)
    cancel_reason: str | None = None


class ConcurrentExecutionError(RuntimeError):
    """Une exécution est déjà en cours sur ce service."""


class ExecutionEngine:
    """Interprète puis exécute un programme sur un adaptateur."""

    def __init__(self, adapter: RobotAdapter, limits=None) -> None:
        self._adapter = adapter
        self._active: ActiveExecution | None = None
        self._counter = itertools.count(1)
        self._clock = time.monotonic
        self._limits = limits

    @property
    def is_running(self) -> bool:
        return self._active is not None and not self._active.stop_signal.requested

    def new_run_id(self) -> str:
        return f"run-{next(self._counter)}-{self._clock():.0f}"

    # -- Lecture de l'état --------------------------------------------------

    async def _read_truth(self) -> RobotTruth:
        """Ce que le service sait réellement de l'instant présent.

        Un champ laissé à `None` signifie « pas mesuré ». On ne le remplace
        jamais par une valeur favorable : cela ferait passer une condition
        sans que personne ne puisse l'expliquer ensuite.
        """
        try:
            status = await self._adapter.get_status()
        except Exception:
            return RobotTruth()

        posture: str | None = None
        raw_posture = getattr(status, "posture", None)
        if raw_posture is not None:
            posture = getattr(raw_posture, "value", str(raw_posture))

        return RobotTruth(
            posture=posture,
            battery_percent=status.battery_percent,
        )

    # -- Exécution ----------------------------------------------------------

    async def execute_program(self, program, run_id: str) -> AsyncIterator[ExecutionEvent]:
        """Interprète puis exécute un programme structuré."""
        if self.is_running:
            raise ConcurrentExecutionError("Un programme est déjà en cours d’exécution.")

        # L'interprétation a lieu AVANT le moindre mouvement : si elle échoue,
        # le robot n'a pas bougé.
        truth = await self._read_truth()
        try:
            interpreter = Interpreter(self._limits, truth)
            commands = interpreter.run(program)
        except ProgramError as exc:
            yield ExecutionEvent(type="error", message=str(exc))
            yield ExecutionEvent(type="execution_finished", reason=FINISH_ERROR)
            return

        async for event in self._execute(commands, run_id):
            yield event

    async def execute(
        self, commands: list[RobotCommand], run_id: str
    ) -> AsyncIterator[ExecutionEvent]:
        """Exécute une suite d'instructions DÉJÀ interprétées.

        Réservé aux tests. Un programme d'enfant passe par
        `execute_program`.
        """
        async for event in self._execute(commands, run_id):
            yield event

    async def _execute(
        self, commands: list[RobotCommand], run_id: str
    ) -> AsyncIterator[ExecutionEvent]:
        if self.is_running:
            raise ConcurrentExecutionError("Un programme est déjà en cours d’exécution.")

        active = ActiveExecution(run_id=run_id, started_at=self._clock())
        self._active = active

        try:
            async for event in self._run(commands, active):
                yield event
        finally:
            await self._finalize(active)

    async def _finalize(self, active: ActiveExecution) -> None:
        """Aucune exécution ne se termine sans avoir demandé l'arrêt.

        Garantit qu'aucune consigne de mouvement ne survit à la fin du
        programme, même en cas d'exception.
        """
        try:
            await self._adapter.request_stop()
        except Exception:
            pass
        if self._active is active:
            self._active = None

    async def _prepare_run(self) -> None:
        """Met le robot en position de marche avant le premier ordre.

        Un échec ici n'interrompt PAS le programme : le SDK sait relever un
        robot avant de bouger, et l'enfant ne doit pas voir une erreur pour
        une posture déjà acquise.
        """
        try:
            await self._adapter.prepare_run()
        except SafetyInterrupt:
            # Le verrouillage de sécurité doit arrêter le programme, pas être
            # avalé comme un simple refus de posture.
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Préparation du robot impossible : %s", exc)

    async def _clearance(self, direction: str) -> float | None:
        """Distance libre annoncée par l'adaptateur, ou `None` si inconnue.

        Une mesure qui échoue ne doit ni inventer un mur, ni inventer une voie
        libre : on la traite comme absente.
        """
        try:
            return await self._adapter.clearance_m(direction)
        except Exception:  # noqa: BLE001 - une mesure absente n'arrête pas tout
            log.exception("La distance libre n'a pas pu être mesurée.")
            return None

    async def _run(
        self, commands: list[RobotCommand], active: ActiveExecution
    ) -> AsyncIterator[ExecutionEvent]:
        # Le robot doit être sur ses quatre pattes avant le premier ordre.
        # S'il est resté assis (fin de programme précédente, test de liaison),
        # il se relève tout seul : l'enfant n'a rien à demander.
        try:
            await self._prepare_run()
        except SafetyInterrupt as exc:
            active.cancel_reason = FINISH_SAFETY
            yield ExecutionEvent(type="error", message=str(exc))
            yield ExecutionEvent(type="execution_finished", reason=FINISH_SAFETY)
            return

        for index, command in enumerate(commands):
            if active.stop_signal.requested:
                yield ExecutionEvent(
                    type="execution_finished", reason=active.cancel_reason or FINISH_STOPPED
                )
                return

            yield ExecutionEvent(type="step_started", index=index, label=command.label())

            # Assez de place ? La carte du lidar est lue AVANT de donner la
            # moindre consigne. Sans mesure (simulateur, carte ou pose
            # périmée), on ne bloque pas : le déplacement se fait comme avant,
            # et le contrôle permanent de l'adaptateur reste la barrière.
            direction = direction_of(command.kind)
            if direction is not None:
                libre = await self._clearance(direction)
                if libre is not None:
                    requis = required_clearance_m(
                        travel_distance_m(command), direction
                    )
                    if libre < requis:
                        detail = obstacle_message(direction, libre)
                        log.info(
                            "Étape %d non faite : %s (libre %.2f m, requis %.2f m)",
                            index,
                            detail,
                            libre,
                            requis,
                        )
                        yield ExecutionEvent(
                            type="step_finished",
                            index=index,
                            label=command.label(),
                            outcome="blocked",
                            message=detail,
                        )
                        # On saute SEULEMENT cette action : la suite du
                        # programme peut très bien être un demi-tour.
                        continue

            try:
                result: CommandOutcome = await self._adapter.execute_command(
                    command, index, active.stop_signal
                )
            except SafetyInterrupt as exc:
                # L'adaptateur a déjà envoyé l'arrêt physique. On termine le
                # programme avec la raison « safety », jamais comme une panne.
                active.cancel_reason = FINISH_SAFETY
                yield ExecutionEvent(
                    type="step_finished",
                    index=index,
                    label=command.label(),
                    outcome="stopped",
                    message=str(exc),
                )
                yield ExecutionEvent(type="execution_finished", reason=FINISH_SAFETY)
                return
            except AdapterError as exc:
                yield ExecutionEvent(
                    type="error",
                    index=index,
                    label=command.label(),
                    message=str(exc),
                )
                yield ExecutionEvent(type="execution_finished", reason=FINISH_ERROR)
                return

            if result.outcome != "blocked":
                yield ExecutionEvent(type="step_completed", index=index, label=command.label())

            measured: dict[str, float] = {}
            if result.measured_distance_cm is not None:
                measured["distanceCm"] = result.measured_distance_cm
            if result.measured_angle_deg is not None:
                measured["angleDeg"] = result.measured_angle_deg

            yield ExecutionEvent(
                type="step_finished",
                index=index,
                label=command.label(),
                outcome=result.outcome,
                measured=measured or None,
                message=result.detail,
            )

            if result.outcome == "stopped":
                yield ExecutionEvent(
                    type="execution_finished", reason=active.cancel_reason or FINISH_STOPPED
                )
                return

            if result.outcome == "failed":
                yield ExecutionEvent(
                    type="error",
                    index=index,
                    label=command.label(),
                    message=result.detail or "Instruction impossible.",
                )
                yield ExecutionEvent(type="execution_finished", reason=FINISH_ERROR)
                return

        yield ExecutionEvent(type="execution_finished", reason=FINISH_COMPLETED)

    # -- Arrêt et bail -----------------------------------------------------

    def request_stop(self, reason: str = FINISH_STOPPED) -> bool:
        """Demande l'arrêt. Retourne `False` si rien n'est en cours."""
        active = self._active
        if active is None:
            return False
        active.cancel_reason = reason
        active.stop_signal.request(reason)
        return True

    def notify_heartbeat(self, now: float) -> None:
        active = self._active
        if active is not None:
            active.last_heartbeat = now

    def heartbeat_age(self, now: float) -> float | None:
        active = self._active
        return None if active is None else now - active.last_heartbeat

    def lease_expired(self, now: float, timeout_ms: int) -> bool:
        age = self.heartbeat_age(now)
        return age is not None and age * 1000.0 > timeout_ms