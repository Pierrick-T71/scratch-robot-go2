"""Tests de la condition d'arrêt d'un déplacement.

Ces tests verrouillent deux propriétés de sécurité :

1. un déplacement qui DÉPASSE sa cible doit s'arrêter quand même (et non
   continuer jusqu'au délai de sécurité) ;
2. un déplacement qui N'ATTEINT PAS sa cible doit finir en « temps écoulé »,
   jamais en « réussi ».
"""

from __future__ import annotations

import pytest

from go2_service.adapters.base import StopSignal
from go2_service.adapters.motion import (
    POSITION_TOLERANCE_CM,
    YAW_TOLERANCE_DEG,
    plan_command,
)
from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.config import load_limits
from go2_service.validation import CommandKind, RobotCommand

SIM_SPEEDUP = 50.0


@pytest.fixture
def limits():
    return load_limits()


def make(limits, **kwargs) -> SimulatedAdapter:
    kwargs.setdefault("tick_multiplier", SIM_SPEEDUP)
    return SimulatedAdapter(limits, **kwargs)


class TestOvershootStops:
    async def test_overshoot_does_not_keep_moving(self, limits):
        """Avec une dérive forte, le robot dépasse : il doit s'arrêter."""
        adapter = make(limits, drift_ratio=0.0, seed=3)
        await adapter.connect()

        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=100), 0, StopSignal()
        )
        assert outcome.outcome == "exact"

        # Le dépassement ne doit pas dépasser un pas de contrôle de plus que
        # la tolérance : c'est le signe que l'arrêt a bien eu lieu à l'approche.
        overshoot = outcome.measured_distance_cm - 100
        period_m = limits.timing.command_tick_seconds * limits.motion.max_linear_speed * 100
        assert overshoot <= POSITION_TOLERANCE_CM + period_m + 1.0

    async def test_reach_uses_lower_threshold(self, limits):
        """Une valeur mesurée proche mais au-dessus de la cible vaut arrivée.

        Le test verrouille la formule par seuil bas : c'est elle qui empêche
        de continuer à avancer en cas de dépassement.
        """
        adapter = make(limits)
        await adapter.connect()
        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=100), 0, StopSignal()
        )
        assert outcome.measured_distance_cm >= 100 - POSITION_TOLERANCE_CM

    async def test_angle_overshoot_stops(self, limits):
        adapter = make(limits)
        await adapter.connect()
        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.TURN_LEFT, angle_deg=180), 0, StopSignal()
        )
        assert outcome.outcome == "exact"
        assert outcome.measured_angle_deg >= 180 - YAW_TOLERANCE_DEG
        # Et il ne doit pas avoir fait un tour complet.
        assert outcome.measured_angle_deg < 180 + YAW_TOLERANCE_DEG + 20


class TestUnderReachedNeverReportsSuccess:
    async def test_stuck_robot_reports_timeout(self, limits):
        """Un robot dont l'état n'avance jamais doit finir en délai dépassé."""
        adapter = make(limits)
        adapter.simulate_stuck = True
        await adapter.connect()

        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=100), 0, StopSignal()
        )
        # Le point essentiel : jamais « réussi ».
        assert outcome.outcome == "timeout"

    async def test_stuck_turn_reports_timeout(self, limits):
        adapter = make(limits)
        adapter.simulate_stuck = True
        await adapter.connect()

        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.TURN_RIGHT, angle_deg=90), 0, StopSignal()
        )
        assert outcome.outcome == "timeout"

    async def test_timeout_stops_at_the_safety_deadline(self, limits):
        """Le délai de sécurité borne la durée, même en cas d'échec."""
        adapter = make(limits)
        adapter.simulate_stuck = True
        await adapter.connect()

        plan = plan_command(
            RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=100), limits
        )
        assert plan is not None

        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=100), 0, StopSignal()
        )
        assert outcome.outcome == "timeout"
        # La distance parcourue correspond au délai, pas à une valeur arbitraire.
        expected_cm = plan.timeout_s * limits.motion.max_linear_speed * 100
        assert outcome.measured_distance_cm == pytest.approx(expected_cm, rel=0.15)

    async def test_timeout_is_longer_than_nominal(self, limits):
        plan = plan_command(RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=100), limits)
        assert plan is not None
        assert plan.timeout_s > plan.nominal_duration_s * 2


class TestStopBlockIsNotAnInterruption:
    async def test_stop_block_completes_normally(self, limits):
        """« S'arrêter » est une instruction, pas une annulation."""
        adapter = make(limits)
        await adapter.connect()

        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.STOP), 0, StopSignal()
        )
        assert outcome.outcome == "exact"