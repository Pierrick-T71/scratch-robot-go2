"""Sémantique du mouvement : durée demandée et angle demandé.

Ces tests verrouillent les deux corrections qui ne se voient pas dans un
simple test de planification :

  1. une translation dure la DURÉE demandée, pas la distance estimée. Une
     commande de 0,5 s à 0,1 m/s doit parcourir ~5 cm, et non s'arrêter
     immédiatement parce que 5 cm - 5 cm de tolérance vaut 0 ;
  2. une rotation est asservie sur le cap MESURÉ et s'arrête dans la bande
     morte, au lieu de dépasser la cible.

Le simulateur applique la même sémantique que l'adaptateur réel : ce sont ces
règles, et non des constantes propres au simulateur, qui sont testées ici.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.base import StopSignal  # noqa: E402
from go2_service.adapters.motion import YAW_BANDE_MORTE_DEG  # noqa: E402
from go2_service.adapters.simulated import SimulatedAdapter  # noqa: E402
from go2_service.config import load_limits  # noqa: E402
from go2_service.validation import CommandKind, RobotCommand  # noqa: E402

LIMITS = load_limits()


def adapter() -> SimulatedAdapter:
    """Simulateur accéléré : 1 s simulée coûte 0,02 s réelle."""
    return SimulatedAdapter(LIMITS, tick_multiplier=20.0, drift_ratio=0.0)


async def execute(
    sim: SimulatedAdapter,
    kind: CommandKind,
    *,
    speed: float = 0.3,
    seconds: float = 1.0,
    angle: float = 0.0,
):
    await sim.connect()
    await sim.prepare_run()
    return await sim.execute_command(
        RobotCommand(
            kind=kind, speed=speed, duration_s=seconds, angle_deg=angle
        ),
        0,
        StopSignal(),
    )


class TestTranslationDuration:
    @pytest.mark.asyncio
    async def test_one_second_at_30_cm_per_second_travels_30_cm(self):
        sim = adapter()
        result = await execute(sim, CommandKind.MOVE_FORWARD)
        assert result.outcome == "exact"
        assert result.measured_distance_cm == pytest.approx(30.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_a_short_move_is_not_swallowed_by_the_position_tolerance(self):
        # 0,5 s à 0,1 m/s = 5 cm. L'ancienne règle « distance - 5 cm » aurait
        # déclaré la cible atteinte à 0 cm : le robot n'aurait pas bougé.
        sim = adapter()
        result = await execute(
            sim, CommandKind.MOVE_FORWARD, speed=0.1, seconds=0.5
        )
        assert result.outcome == "exact"
        assert result.measured_distance_cm == pytest.approx(5.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_a_lateral_move_is_timed_too(self):
        # `distance_cm` vaut 0 pour un déplacement latéral : la durée est la
        # seule cible, et elle doit être honorée.
        sim = adapter()
        result = await execute(sim, CommandKind.MOVE_LEFT)
        assert result.outcome == "exact"
        assert result.measured_distance_cm == pytest.approx(30.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_a_stuck_robot_times_out_instead_of_pretending(self):
        sim = adapter()
        sim.simulate_stuck = True
        result = await execute(sim, CommandKind.MOVE_FORWARD, seconds=1.0)
        assert result.outcome == "timeout"


class TestRotationServo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kind,angle",
        [
            (CommandKind.TURN_LEFT, 45.0),
            (CommandKind.TURN_RIGHT, 45.0),
            (CommandKind.TURN_LEFT, 90.0),
            (CommandKind.TURN_RIGHT, 90.0),
            (CommandKind.TURN_LEFT, 180.0),
        ],
    )
    async def test_the_measured_angle_matches_the_request(self, kind, angle):
        sim = adapter()
        seconds = (angle / 180.0) * 3.141592653589793 / 0.5
        result = await execute(
            sim, kind, speed=0.5, seconds=seconds, angle=angle
        )
        assert result.outcome == "exact"
        assert result.measured_angle_deg == pytest.approx(
            angle, abs=YAW_BANDE_MORTE_DEG + 0.6
        )

    @pytest.mark.asyncio
    async def test_the_robot_never_spins_past_the_target(self):
        # Sans servo, 90° demandés donnaient 139°. Ici l'écart final doit
        # rester dans la bande morte, quel que soit le nombre de pas.
        sim = adapter()
        result = await execute(
            sim,
            CommandKind.TURN_LEFT,
            speed=0.5,
            seconds=90.0 / 180.0 * 3.141592653589793 / 0.5,
            angle=90.0,
        )
        assert result.measured_angle_deg is not None
        assert result.measured_angle_deg <= 90.0 + YAW_BANDE_MORTE_DEG + 0.6
