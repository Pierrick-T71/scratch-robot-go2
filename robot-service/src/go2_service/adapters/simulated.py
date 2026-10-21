"""Adaptateur de simulation.

N'envoie JAMAIS de commande physique : il n'a aucun accès au SDK et aucune
socket réseau. Il permet de développer, tester et démontrer l'application
sans le robot.

Il simule fidèlement ce qui compte pour la logique :
  - une odométrie qui dérive (le robot ne va pas droit tout seul) ;
  - un état mesurable, permettant de distinguer « mesuré » de « supposé » ;
  - des pannes de connexion et des erreurs d'instruction, pour tester
    les chemins d'échec de la sécurité.

La dérive est VOLONTAIRE : sans elle, le test fermé ne prouverait rien.
"""

from __future__ import annotations

import asyncio
import math
import random

from ..config import Limits
from ..validation import Capability, CommandKind, RobotCommand
from .base import (
    AdapterError,
    CommandOutcome,
    Posture,
    RobotState,
    Status,
    StopSignal,
)
from .motion import (
    YAW_BANDE_MORTE_DEG,
    assert_speed_within_limits,
    plan_command,
    travelled_distance_cm,
    yaw_rate_for_remaining,
)

#: Capacités complètes du robot simulé (mêmes noms que le service réel).
SIMULATED_CAPABILITIES = frozenset(
    {
        Capability.MOVEMENT,
        Capability.POSTURE,
        Capability.WAIT,
        Capability.STOP,
        Capability.VARIABLE,
        Capability.BROADCAST,
        Capability.SENSOR_STATE,
        Capability.SENSOR_OBSTACLE,
    }
)


class SimulatedAdapter:
    """Simulateur déterministe et paramétrable."""

    name = "simulation"
    physical_commands_enabled = False

    def __init__(
        self,
        limits: Limits,
        *,
        tick_multiplier: float = 1.0,
        drift_ratio: float = 0.02,
        seed: int = 0,
    ) -> None:
        """
        `tick_multiplier` accélère (ou ralentit) le TEMPS SIMULÉ : chaque
        période de contrôle avance l'horloge simulée de `tick_multiplier`
        fois la période réelle. Les tests l'utilisent pour vérifier les
        chemins d'arrêt (délais de sécurité, interruption) sans attendre en
        vrai. La logique testée est par ailleurs identique.

        `drift_ratio` introduit une erreur de parcours : sans elle, le test
        fermé ne prouverait rien.
        """
        if tick_multiplier <= 0:
            raise ValueError("tick_multiplier doit être strictement positif.")

        self._limits = limits
        self._period = limits.timing.command_tick_seconds
        self._tick_multiplier = tick_multiplier
        # Pas de temps réel minimal pour ne pas boucler à pleine vitesse.
        self._real_sleep = max(0.001, self._period / 50.0)
        self._drift_ratio = drift_ratio
        self._random = random.Random(seed)

        self._connected = False
        self._state = RobotState.UNKNOWN
        self._position = [0.0, 0.0, 0.0]
        self._yaw = 0.0
        self._battery = 100.0
        self._posture = Posture.SIT

        # Points d'injection de panne, pour les tests.
        self.fail_next_command = False
        self.simulate_disconnect_during_motion = False
        self.simulate_stuck = False

    # -- Cycle de vie ------------------------------------------------------

    async def connect(self) -> None:
        await asyncio.sleep(0)
        self._connected = True
        self._state = RobotState.IDLE

    async def disconnect(self) -> None:
        self._connected = False
        self._state = RobotState.DISCONNECTED
        self._position = [0.0, 0.0, 0.0]
        self._yaw = 0.0

    def supports(self, capability: Capability) -> bool:
        return capability in SIMULATED_CAPABILITIES

    # -- État --------------------------------------------------------------

    async def get_status(self) -> Status:
        if not self._connected:
            return Status(
                connected=False,
                state=RobotState.DISCONNECTED,
                capabilities=SIMULATED_CAPABILITIES,
                blocked_reason="Le simulateur n’est pas connecté.",
            )
        return Status(
            connected=True,
            state=self._state,
            capabilities=SIMULATED_CAPABILITIES,
            blocked_reason=None,
            position_m=(self._position[0], self._position[1], self._position[2]),
            yaw_rad=self._yaw,
            battery_percent=self._battery,
            posture=self._posture,
        )

    # -- Exécution ---------------------------------------------------------

    async def prepare_run(self) -> None:
        """Le robot simulé se met sur ses quatre pattes avant de bouger.

        Même contrat que l'adaptateur physique : la posture de départ d'un
        programme est toujours « debout ».
        """
        if self._posture == Posture.SIT:
            self._posture = Posture.STAND

    async def execute_command(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        if not self._connected:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        if self.fail_next_command:
            self.fail_next_command = False
            raise AdapterError("Le robot a refusé la commande.", recoverable=True)

        match command.kind:
            case CommandKind.WAIT:
                return await self._do_wait(command.duration_s, index, should_stop)
            case CommandKind.STAND_UP:
                return await self._do_posture(Posture.STAND, index)
            case CommandKind.SIT_DOWN:
                return await self._do_posture(Posture.SIT, index)
            case CommandKind.LIE_DOWN:
                return await self._do_posture(Posture.LIE_DOWN, index)
            case CommandKind.BALANCE:
                return await self._do_posture(Posture.BALANCE, index)
            case CommandKind.FINGER_HEART:
                # Le geste simulé : un bref mouvement, sans déplacement.
                return await self._do_wait(1.5, index, should_stop)
            case CommandKind.SALUTE:
                # Saluer : un bref mouvement, sans deplacement.
                return await self._do_wait(1.5, index, should_stop)
            case CommandKind.STRETCH:
                # S'étirer dure un peu plus longtemps qu'un salut.
                return await self._do_wait(3.0, index, should_stop)
            case CommandKind.FRONT_JUMP:
                # Le saut simule : un bref mouvement, sans deplacement.
                return await self._do_wait(1.5, index, should_stop)
            case CommandKind.STOP:
                await self.request_stop()
                # Un bloc « Arrêter le déplacement » est une instruction comme
                # une autre : elle s'accomplit et le programme continue.
                # Seule une INTERRUPTION (bouton Arrêter, bail) renvoie
                # l'issue « stopped ».
                return CommandOutcome(
                    index=index, outcome="exact", detail="Arrêt exécuté."
                )
            case _:
                return await self._do_move(command, index, should_stop)

    def read_sensor(self, what: str) -> float | None:
        """Mesure « simulée », explicitement étiquetée comme telle.

        ⚠️ Cette valeur n'est PAS une mesure du robot. Elle n'est lue que si
        l'adaptateur en a la capacité, et le frontend la présente comme
        « simulation ». Aucun chiffre n'est inventé pour `batterie` : on
        renvoie l'état réel de la simulation, qui est un fait.
        """
        if what == "batterie":
            return self._battery
        if what == "obstacle":
            # Le simulateur ne modélise pas d'obstacle : aucune valeur n'est
            # fabriquée. Renvoyer 0 Reviendrait à dire « l'obstacle est collé ».
            return None
        return None

    async def request_stop(self) -> None:
        self._state = RobotState.IDLE
        # Aucun report de position : on ne simule pas d'inertie résiduelle.

    async def camera_frame(self) -> bytes | None:
        """Le simulateur n'a pas de caméra : aucune image, jamais inventée."""
        return None

    async def lidar_points(self) -> list[list[float]] | None:
        """Le simulateur n'a pas de lidar : aucun point, jamais inventé."""
        return None

    async def lidar_volume(self) -> dict[str, Any] | None:
        """Le simulateur n'a pas de lidar : aucun volume, jamais inventé."""
        return None

    async def set_autonome(self, actif: bool) -> bool:
        """Le simulateur ne marche pas tout seul : le mode est refusé."""
        return False

    # -- Internes ----------------------------------------------------------

    async def _do_wait(
        self, seconds: float, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        remaining = max(0.0, seconds)
        while remaining > 0:
            if should_stop.requested:
                return CommandOutcome(index=index, outcome="stopped")
            step = min(self._sim_step(), remaining)
            await asyncio.sleep(self._real_sleep)
            remaining -= step
        return CommandOutcome(index=index, outcome="exact")

    def _sim_step(self) -> float:
        """Durée simulée correspondant à un pas de boucle."""
        return self._period * self._tick_multiplier

    async def _do_posture(self, posture: Posture, index: int) -> CommandOutcome:
        # Une transition de posture n'a pas de confirmation mesurée par le SDK.
        # On le dit explicitement plutôt que d'inventer une mesure.
        self._posture = posture
        return CommandOutcome(
            index=index,
            outcome="exact",
            detail="Posture appliquée (aucune mesure fournie par le SDK).",
        )

    async def _do_move(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        plan = plan_command(command, self._limits)
        if plan is None:
            raise AdapterError(f"Commande non gérée par le simulateur : {command.kind.value}")

        # Protection de dernier niveau, avant toute « publication ».
        assert_speed_within_limits(plan, self._limits)

        if plan.angle_deg > 0:
            return await self._tourner(plan, index, should_stop)
        return await self._translater(plan, index, should_stop)

    async def _translater(
        self, plan, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        """Tient la vitesse pendant la durée demandée, puis s'arrête.

        Même sémantique que l'adaptateur réel : la durée est la cible, pas la
        distance. Cela couvre aussi les déplacements latéraux, dont
        `distance_cm` vaut 0.
        """
        start_xy = (self._position[0], self._position[1])
        self._state = RobotState.MOVING
        elapsed = 0.0
        step = self._sim_step()

        while True:
            if should_stop is not None and should_stop.requested:
                await self.request_stop()
                return CommandOutcome(index=index, outcome="stopped")

            await asyncio.sleep(self._real_sleep)
            elapsed += step

            # Défaillance réseau en cours de mouvement.
            if self.simulate_disconnect_during_motion:
                self.simulate_disconnect_during_motion = False
                self._connected = False
                self._state = RobotState.DISCONNECTED
                raise AdapterError(
                    "La liaison avec le robot a été perdue.", recoverable=True
                )

            self._advance(
                plan.linear_speed_mps,
                plan.lateral_speed_mps,
                plan.angular_speed_rps,
                step,
            )
            self._battery = max(0.0, self._battery - self._period * 0.02)

            if (
                elapsed >= plan.nominal_duration_s - 1e-9
                and not self.simulate_stuck
            ):
                await self.request_stop()
                return self._outcome_for(index, plan, start_xy, "exact")

            if elapsed >= plan.timeout_s - 1e-9:
                # Dépassement : arrêt de sécurité, et on ne prétend PAS que la
                # cible a été atteinte.
                await self.request_stop()
                return self._outcome_for(index, plan, start_xy, "timeout")

    async def _tourner(
        self, plan, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        """Asservit la rotation sur le cap simulé, comme le fait le réel.

        Le simulateur ne doit pas « réussir » une rotation que le robot réel
        raterait : on applique donc la même bande morte et le même servo.
        """
        start_yaw = self._yaw
        direction = 1.0 if plan.angular_speed_rps >= 0.0 else -1.0
        max_rate = abs(plan.angular_speed_rps)
        self._state = RobotState.MOVING
        elapsed = 0.0
        step = self._sim_step()

        while True:
            if should_stop is not None and should_stop.requested:
                await self.request_stop()
                return CommandOutcome(index=index, outcome="stopped")

            ecart = math.degrees(
                direction * math.radians(plan.angle_deg) - (self._yaw - start_yaw)
            )
            # `ecart` est exprimé dans le sens de la rotation : positif tant
            # qu'il reste de l'angle à parcourir, négatif en cas de dépassement.
            if abs(ecart) <= YAW_BANDE_MORTE_DEG:
                await self.request_stop()
                return self._outcome_for(
                    index, plan, None, "exact", start_yaw=start_yaw
                )

            rate = yaw_rate_for_remaining(abs(ecart), max_rate)
            await asyncio.sleep(self._real_sleep)
            elapsed += step
            if not self.simulate_stuck:
                self._advance(0.0, 0.0, direction * rate, step)
            self._battery = max(0.0, self._battery - self._period * 0.02)

            if elapsed >= plan.timeout_s - 1e-9:
                await self.request_stop()
                return self._outcome_for(
                    index, plan, None, "timeout", start_yaw=start_yaw
                )

    def _advance(self, vx: float, vy: float, vyaw: float, dt: float) -> None:
        """Intègre une étape de déplacement, avec une dérive simulée."""
        # Dérive latérale : un vrai quadrupède ne suit pas une ligne droite.
        drift = self._random.uniform(-self._drift_ratio, self._drift_ratio)

        dx = vx * dt + vy * dt
        dy = vx * drift * dt
        # Rotation de la position du robot autour de son centre.
        cos_y = math.cos(self._yaw)
        sin_y = math.sin(self._yaw)
        self._position[0] += dx * cos_y - dy * sin_y
        self._position[1] += dx * sin_y + dy * cos_y
        self._yaw += vyaw * dt

    def _outcome_for(
        self,
        index: int,
        plan,
        start_xy: tuple[float, float] | None,
        outcome: str,
        start_yaw: float | None = None,
    ) -> CommandOutcome:
        """Construit le résultat à partir de l'état RÉELLEMENT simulé.

        La valeur mesurée vient de l'intégration, jamais de la consigne. C'est
        ce qui permet à l'interface d'afficher « mesuré » honnêtement.
        """
        if plan.angle_deg <= 0:
            measured = (
                travelled_distance_cm(
                    start_xy, (self._position[0], self._position[1])
                )
                if start_xy is not None
                else 0.0
            )
            return CommandOutcome(
                index=index, outcome=outcome, measured_distance_cm=round(measured, 1)
            )
        # Le cap simulé n'a pas de limite à ±π : la différence directe donne
        # l'angle parcouru, y compris au-delà de 180°.
        depart = start_yaw if start_yaw is not None else self._yaw
        measured_angle = abs(math.degrees(self._yaw - depart))
        return CommandOutcome(
            index=index, outcome=outcome, measured_angle_deg=round(measured_angle, 1)
        )
