"""Navigation autonome sécurisée avec évitement d'obstacles et comportements canins.

En mode autonome, le robot explore son environnement de manière fluide :
- Il avance à vitesse modérée et maîtrisée (0,25 m/s).
- Il scrute en permanence la distance libre devant lui via le LiDAR.
- Dès qu'un obstacle entre dans le périmètre d'anticipation (distance <= 0,65 m, soit ~30 cm du museau) :
  1. Il s'arrête immédiatement et proprement à ~30 cm de l'obstacle sans le percuter.
  2. Il interroge les dégagements latéraux gauche et droit.
  3. Il pivote vers le côté le plus ouvert pour contourner l'obstacle et changer de direction.
  4. Dès que la voie est dégagée, il reprend sa marche avant.
  5. S'il est complètement enfermé dans une impasse où aucun dégagement n'est possible, il coupe
     le mode autonome avec un message d'erreur explicite.
- De temps en temps (toutes les 20 à 35 secondes), comme un vrai chien, il marque une pause
  pour s'étirer, s'asseoir un moment avant de se relever, ou faire un petit coucou de la patte.
- Toute demande d'arrêt (bouton carré rouge Scratch, mode manuel, veille)
  interrompt immédiatement la navigation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import time
from typing import Any, Awaitable, Callable

from .adapters.base import RobotAdapter, RobotState, StopSignal
from .validation import CommandKind, RobotCommand

log = logging.getLogger(__name__)


class AutonomousNotActive(RuntimeError):
    """Le mode autonome n'est pas actif."""


class AutonomousControl:
    """Gestionnaire de navigation autonome du robot avec évitement et comportements vivants."""

    AUTONOMOUS_SPEED_MPS = 0.25
    AUTONOMOUS_TURN_SPEED_RPS = 0.8
    OBSTACLE_THRESHOLD_M = 0.65  # Arrêt net à ~30 cm de l'obstacle (museau)
    TICK_INTERVAL_S = 0.1

    def __init__(self, adapter: RobotAdapter) -> None:
        self._adapter = adapter
        self._active = False
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._last_stop_reason: str | None = None
        self._on_stop: Callable[[str | None], Awaitable[None]] | None = None
        self._prochaine_animation_at: float = 0.0
        self._animating: bool = False

    @property
    def active(self) -> bool:
        """Indique si la navigation autonome est en cours."""
        return self._active

    @property
    def last_stop_reason(self) -> str | None:
        """Dernière raison d'arrêt du mode autonome."""
        return self._last_stop_reason

    def set_on_stop(self, callback: Callable[[str | None], Awaitable[None]] | None) -> None:
        """Définit le rappel asynchrone invoqué lors de l'arrêt du mode autonome."""
        self._on_stop = callback

    async def start(self) -> tuple[bool, str | None]:
        """Démarre la navigation autonome."""
        async with self._lock:
            if self._active:
                return True, None

            status = await self._adapter.get_status()
            if not status.connected and self._adapter.name == "webrtc":
                return False, "Le robot n’est pas connecté."

            entrer = getattr(self._adapter, "enter_autonomous_mode", None)
            if entrer is not None:
                try:
                    await entrer()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Impossible d'engager le mode autonome sur l'adaptateur : %s", exc)
                    return False, f"Impossible d'engager le mode autonome ({exc})."

            if hasattr(self._adapter, "obstacle_safety_enabled") and not self._adapter.obstacle_safety_enabled:
                self._adapter.obstacle_safety_enabled = True
                log.info("Mode autonome : sécurité obstacle activée sur l'adaptateur.")

            self._active = True
            self._last_stop_reason = None
            self._animating = False
            self._prochaine_animation_at = time.monotonic() + random.uniform(20.0, 35.0)
            self._task = asyncio.create_task(self._navigation_loop())
            log.info("Mode autonome démarré.")
            return True, None

    async def stop(self, reason: str | None = None) -> None:
        """Arrête la navigation autonome et immobilise le robot."""
        async with self._lock:
            if not self._active and self._last_stop_reason == reason:
                return
            was_active = self._active
            self._active = False
            if reason:
                self._last_stop_reason = reason

            if self._task is not None and asyncio.current_task() != self._task:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
                self._task = None

            quitter = getattr(self._adapter, "exit_autonomous_mode", None)
            if quitter is not None:
                with contextlib.suppress(Exception):
                    await quitter()
            else:
                with contextlib.suppress(Exception):
                    await self._adapter.request_stop()
            log.info("Mode autonome arrêté (raison : %s).", reason or "arrêt utilisateur")

            if was_active and self._on_stop is not None:
                with contextlib.suppress(Exception):
                    await self._on_stop(self._last_stop_reason)

    async def _navigation_loop(self) -> None:
        """Boucle principale d'exploration avec évitement d'obstacles et vie canine."""
        try:
            while self._active:
                # 1. Vérification de l'état du robot
                status = await self._adapter.get_status()
                if not status.connected:
                    await self.stop(reason="Le robot a été déconnecté.")
                    break
                if status.safety_reason:
                    await self.stop(reason=f"Sécurité : {status.safety_reason}")
                    break
                if status.blocked_reason:
                    await self.stop(reason=f"Le robot est bloqué ({status.blocked_reason}).")
                    break

                # 2. Interrogation de la distance libre devant
                clearance = None
                with contextlib.suppress(Exception):
                    clearance = await self._adapter.clearance_m("forward")

                if clearance is not None and clearance <= self.OBSTACLE_THRESHOLD_M:
                    # Obstacle à ~30 cm du museau : arrêt net et changement de direction
                    dist_cm = max(0, int(round((clearance - 0.30) * 100)))
                    log.info(
                        "Mode autonome : obstacle détecté à ~%d cm. Arrêt et changement de direction.",
                        dist_cm,
                    )
                    self._adapter.manual_velocity("forward", speed_mps=0.0, turn_speed_rps=0.0)
                    await asyncio.sleep(0.15)
                    if not self._active:
                        break

                    # Analyse des dégagements latéraux
                    left_c = None
                    right_c = None
                    with contextlib.suppress(Exception):
                        left_c = await self._adapter.clearance_m("left")
                    with contextlib.suppress(Exception):
                        right_c = await self._adapter.clearance_m("right")

                    val_left = left_c if left_c is not None and not math.isinf(left_c) else (999.0 if left_c is not None else 1.0)
                    val_right = right_c if right_c is not None and not math.isinf(right_c) else (999.0 if right_c is not None else 1.0)

                    if abs(val_left - val_right) < 0.2:
                        turn_direction = random.choice(["turn_left", "turn_right"])
                    elif val_left > val_right:
                        turn_direction = "turn_left"
                    else:
                        turn_direction = "turn_right"

                    log.info("Mode autonome : virage vers %s (G: %s, D: %s)", turn_direction, left_c, right_c)

                    # Pivot d'évitement (~1.5 s, soit ~70°)
                    for _ in range(15):
                        if not self._active:
                            break
                        self._adapter.manual_velocity(
                            turn_direction,
                            speed_mps=0.0,
                            turn_speed_rps=self.AUTONOMOUS_TURN_SPEED_RPS,
                        )
                        await asyncio.sleep(0.1)

                    self._adapter.manual_velocity("forward", speed_mps=0.0, turn_speed_rps=0.0)
                    await asyncio.sleep(0.2)
                    if not self._active:
                        break

                    # Vérification de la voie après virage
                    clearance_apres = None
                    with contextlib.suppress(Exception):
                        clearance_apres = await self._adapter.clearance_m("forward")

                    # Si c'est un coin, pivoter encore un peu dans la même direction
                    essais = 0
                    while self._active and clearance_apres is not None and clearance_apres <= self.OBSTACLE_THRESHOLD_M and essais < 2:
                        essais += 1
                        log.info("Mode autonome : voie encore obstruée (%.2f m), rotation supplémentaire...", clearance_apres)
                        for _ in range(12):  # ~1.2 s (~55°)
                            if not self._active:
                                break
                            self._adapter.manual_velocity(
                                turn_direction,
                                speed_mps=0.0,
                                turn_speed_rps=self.AUTONOMOUS_TURN_SPEED_RPS,
                            )
                            await asyncio.sleep(0.1)
                        self._adapter.manual_velocity("forward", speed_mps=0.0, turn_speed_rps=0.0)
                        await asyncio.sleep(0.2)
                        with contextlib.suppress(Exception):
                            clearance_apres = await self._adapter.clearance_m("forward")

                    if clearance_apres is not None and clearance_apres <= self.OBSTACLE_THRESHOLD_M and essais >= 2:
                        reason = "Espace bloqué : impossible de trouver une issue après pivot."
                        log.warning("Mode autonome : arrêt sur impasse. %s", reason)
                        await self.stop(reason=reason)
                        break

                    # Voie dégagée : on repart
                    continue

                # 3. Comportements canins périodiques (« comme un vrai chien »)
                now = time.monotonic()
                if now >= self._prochaine_animation_at and not self._animating:
                    await self._execute_dog_behavior()
                    continue

                # 4. Marche avant fluide et régulière
                self._adapter.manual_velocity(
                    "forward",
                    speed_mps=self.AUTONOMOUS_SPEED_MPS,
                    turn_speed_rps=0.0,
                )
                await asyncio.sleep(self.TICK_INTERVAL_S)

        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.error("Erreur inattendue dans la boucle autonome : %s", exc)
        finally:
            with contextlib.suppress(Exception):
                self._adapter.manual_velocity("forward", speed_mps=0.0, turn_speed_rps=0.0)
            self._active = False

    async def _execute_dog_behavior(self) -> None:
        """Pause naturelle : s'étirer, s'asseoir ou saluer comme un chien."""
        self._animating = True
        try:
            # Ralentir et s'arrêter en douceur
            self._adapter.manual_velocity("forward", speed_mps=0.0, turn_speed_rps=0.0)
            await asyncio.sleep(0.3)
            if not self._active:
                return

            choice = random.choice(["stretch", "sit", "salute"])
            log.info("Mode autonome : animation canine déclenchée -> %s", choice)
            stop_sig = StopSignal()

            if choice == "stretch":
                # Le chien s'étire
                with contextlib.suppress(Exception):
                    await self._adapter.execute_command(
                        RobotCommand(kind=CommandKind.STRETCH),
                        index=0,
                        should_stop=stop_sig,
                    )
                await asyncio.sleep(0.5)

            elif choice == "sit":
                # Le chien s'assoit, reste assis quelques secondes en regardant autour, puis se relève
                with contextlib.suppress(Exception):
                    await self._adapter.execute_command(
                        RobotCommand(kind=CommandKind.SIT_DOWN),
                        index=0,
                        should_stop=stop_sig,
                    )
                pause_s = random.uniform(4.0, 7.0)
                end_pause = time.monotonic() + pause_s
                while time.monotonic() < end_pause and self._active:
                    await asyncio.sleep(0.2)

                if self._active:
                    with contextlib.suppress(Exception):
                        await self._adapter.execute_command(
                            RobotCommand(kind=CommandKind.STAND_UP),
                            index=0,
                            should_stop=stop_sig,
                        )
                    await asyncio.sleep(0.5)

            elif choice == "salute":
                # Le chien fait un coucou de la patte
                with contextlib.suppress(Exception):
                    await self._adapter.execute_command(
                        RobotCommand(kind=CommandKind.SALUTE),
                        index=0,
                        should_stop=stop_sig,
                    )
                await asyncio.sleep(0.5)

        finally:
            self._animating = False
            self._prochaine_animation_at = time.monotonic() + random.uniform(20.0, 35.0)
