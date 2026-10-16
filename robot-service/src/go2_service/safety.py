"""Chien de garde de sécurité.

RAISON D'ÊTRE
-------------
`SportClient.Move()` définit une CONSIGNE DE VITESSE PERSISTANTE. L'exemple
officiel du SDK ne fait jamais de `StopMove()` en sortie de boucle. Autrement
dit : si ce service s'arrête, se fige ou perd le réseau, le robot peut
continuer de marcher avec sa dernière vitesse.

Conséquence : la liaison frontend ↔ service est un BAIL. Tant que le frontend
n'envoie pas de battements, le service déclare la liaison perdue et déclenche
l'arrêt. C'est le seul mécanisme qui protège le robot si l'interface est
fermée, plantée ou déconnectée.

Ce que ce module ne fait PAS : il ne remplace ni l'arrêt d'urgence physique,
ni la télécommande, ni la surveillance d'un adulte.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from .adapters.base import RobotAdapter
from .config import Limits
from .execution import FINISH_SAFETY, ExecutionEngine

log = logging.getLogger(__name__)


@dataclass
class WatchdogResult:
    """Issue d'une.tick de surveillance."""

    triggered: bool
    reason: str | None = None


class SafetyWatchdog:
    """Surveille le bail et déclenche l'arrêt en cas de rupture."""

    def __init__(self, engine: ExecutionEngine, adapter: RobotAdapter, limits: Limits) -> None:
        self._engine = engine
        self._adapter = adapter
        self._limits = limits
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        #: Nombre d'arrêts déclenchés par la sécurité (statistique et test).
        self.trips = 0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="go2-watchdog")

    async def stop(self) -> None:
        self._stopping.set()
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        # Le chien surveille au tiers du délai de bail : marge pour agir avant
        # expiration, sans consume CPU inutile.
        interval = max(0.05, self._limits.safety.lease_timeout_ms / 3000.0)
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass
            self.tick()

    def tick(self) -> WatchdogResult:
        """Un tour de surveillance. Synchrone et testable isolément."""
        if not self._engine.is_running:
            return WatchdogResult(triggered=False)

        now = time.monotonic()
        if not self._engine.lease_expired(now, self._limits.safety.lease_timeout_ms):
            return WatchdogResult(triggered=False)

        self.trips += 1
        reason = (
            "Bail expiré : l’interface a cessé de répondre. "
            "Arrêt de sécurité déclenché."
        )
        log.warning("%s (total: %d)", reason, self.trips)
        self._engine.request_stop(FINISH_SAFETY)
        return WatchdogResult(triggered=True, reason=reason)

    async def emergency_stop(self) -> None:
        """Arrêt immédiat, sans condition d'exécution en cours.

        Utilisé à l'arrêt du service et lors des erreurs non rattrapables.
        """
        self._engine.request_stop(FINISH_SAFETY)
        try:
            await self._adapter.request_stop()
        except Exception:
            # Dernier recours : on ne peut rien faire de plus ici.
            log.exception("Arrêt d'urgence : l'adaptateur a échoué.")