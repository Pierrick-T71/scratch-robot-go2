"""Moteur d'exécution des programmes.

Rôles :
  - exécuter les instructions une par une, dans l'ordre ;
  - propager l'arrêt demandé à l'instruction en cours ;
  - interdire toute exécution concurrente ;
  - ne jamais déclarer un déplacement « réussi » sans mesure.

Le moteur ne connaît que le contrat `RobotAdapter` : aucune notion de SDK.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from .adapters.base import AdapterError, CommandOutcome, RobotAdapter, StopSignal
from .validation import RobotCommand

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
    """Exécute un programme sur un adaptateur."""

    def __init__(self, adapter: RobotAdapter) -> None:
        self._adapter = adapter
        self._active: ActiveExecution | None = None
        self._counter = itertools.count(1)
        self._clock = time.monotonic

    @property
    def is_running(self) -> bool:
        return self._active is not None and not self._active.stop_signal.requested

    def new_run_id(self) -> str:
        return f"run-{next(self._counter)}-{self._clock():.0f}"

    async def execute(
        self, commands: list[RobotCommand], run_id: str
    ) -> AsyncIterator[ExecutionEvent]:
        """Exécute le programme et produit les événements au fil de l'eau.

        Lever `ConcurrentExecutionError` si une exécution est déjà active.
        """
        if self.is_running:
            raise ConcurrentExecutionError(
                "Un programme est déjà en cours d’exécution."
            )

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

    async def _run(
        self, commands: list[RobotCommand], active: ActiveExecution
    ) -> AsyncIterator[ExecutionEvent]:
        for index, command in enumerate(commands):
            if active.stop_signal.requested:
                yield ExecutionEvent(
                    type="execution_finished", reason=active.cancel_reason or FINISH_STOPPED
                )
                return

            yield ExecutionEvent(type="step_started", index=index, label=command.label())

            try:
                result: CommandOutcome = await self._adapter.execute_command(
                    command, index, active.stop_signal
                )
            except AdapterError as exc:
                yield ExecutionEvent(
                    type="error",
                    index=index,
                    label=command.label(),
                    message=str(exc),
                )
                yield ExecutionEvent(type="execution_finished", reason=FINISH_ERROR)
                return

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