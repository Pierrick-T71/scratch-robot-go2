"""Planification de mouvement : bornes et délais de sécurité.

Le SDK Go2 ne connaît que des VITESSES. Ces tests verrouillent le calcul des
délais : une marge trop courte laisserait le robot pousser contre un obstacle
avant l'arrêt, une marge trop longue retarderait l'arrêt sur un robot qui
glisse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.base import AdapterError, MotionPlan  # noqa: E402
from go2_service.adapters.motion import (  # noqa: E402
    MOVE_TIMEOUT_MARGIN,
    POSITION_TOLERANCE_CM,
    YAW_TOLERANCE_DEG,
    assert_speed_within_limits,
    plan_command,
    shortest_angular_difference_deg,
    timeout_for,
    travelled_distance_cm,
)
from go2_service.config import load_limits  # noqa: E402
from go2_service.validation import CommandKind, RobotCommand  # noqa: E402

LIMITS = load_limits()


def move(kind=CommandKind.MOVE_FORWARD, speed=0.2, seconds=2.0) -> RobotCommand:
    return RobotCommand(kind=kind, speed=speed, duration_s=seconds)


class TestPlanCommand:
    def test_a_forward_move_carries_its_speed_and_duration(self):
        plan = plan_command(move(seconds=3.0), LIMITS)
        assert plan is not None
        assert plan.linear_speed_mps == pytest.approx(0.2)
        assert plan.nominal_duration_s == pytest.approx(3.0)

    def test_a_backward_move_has_a_negative_speed(self):
        plan = plan_command(move(kind=CommandKind.MOVE_BACKWARD), LIMITS)
        assert plan is not None
        assert plan.linear_speed_mps < 0

    @pytest.mark.parametrize(
        "kind,sign",
        [(CommandKind.MOVE_LEFT, 1), (CommandKind.MOVE_RIGHT, -1)],
    )
    def test_a_lateral_move_uses_the_lateral_channel(self, kind, sign):
        plan = plan_command(move(kind=kind), LIMITS)
        assert plan is not None
        assert plan.lateral_speed_mps == pytest.approx(0.2 * sign)
        assert plan.linear_speed_mps == pytest.approx(0.0)

    @pytest.mark.parametrize(
        "kind,sign",
        [(CommandKind.TURN_LEFT, 1), (CommandKind.TURN_RIGHT, -1)],
    )
    def test_a_rotation_uses_the_angular_channel(self, kind, sign):
        plan = plan_command(
            RobotCommand(kind=kind, speed=0.5, duration_s=3.0, angle_deg=90), LIMITS
        )
        assert plan is not None
        assert plan.angular_speed_rps == pytest.approx(sign * LIMITS.motion.max_angular_speed)

    def test_a_rotation_keeps_the_measured_target(self):
        # L'angle demandé est une CIBLE MESURÉE, pas une reconstruction.
        plan = plan_command(
            RobotCommand(
                kind=CommandKind.TURN_LEFT,
                speed=0.5,
                duration_s=3.0,
                angle_deg=45,
            ),
            LIMITS,
        )
        assert plan is not None
        assert plan.angle_deg == pytest.approx(45.0)

    @pytest.mark.parametrize(
        "kind",
        [
            CommandKind.WAIT,
            CommandKind.STAND_UP,
            CommandKind.SIT_DOWN,
            CommandKind.BALANCE,
            CommandKind.STOP,
        ],
    )
    def test_a_non_motion_command_has_no_plan(self, kind):
        assert plan_command(RobotCommand(kind=kind), LIMITS) is None

    def test_the_timeout_is_longer_than_the_request(self):
        plan = plan_command(move(seconds=2.0), LIMITS)
        assert plan is not None
        assert plan.timeout_s > plan.nominal_duration_s


class TestSpeedGuard:
    def test_a_normal_plan_passes(self):
        plan = plan_command(move(speed=LIMITS.motion.max_linear_speed), LIMITS)
        assert plan is not None
        assert_speed_within_limits(plan, LIMITS)

    @pytest.mark.parametrize("factor", [2, 10])
    def test_an_over_limit_linear_speed_is_refused(self, factor):
        plan = MotionPlan(
            linear_speed_mps=LIMITS.motion.max_linear_speed * factor,
            angular_speed_rps=0.0,
            nominal_duration_s=1.0,
            timeout_s=2.0,
        )
        with pytest.raises(AdapterError, match="linéaire"):
            assert_speed_within_limits(plan, LIMITS)

    @pytest.mark.parametrize("factor", [2, 10])
    def test_an_over_limit_lateral_speed_is_refused(self, factor):
        # ⚠️ Régression : ce canal n'était pas vérifié. `Move(0, 3.0, 0)`
        # passait sur un robot limité à 0,3 m/s.
        plan = MotionPlan(
            linear_speed_mps=0.0,
            angular_speed_rps=0.0,
            nominal_duration_s=1.0,
            timeout_s=2.0,
            lateral_speed_mps=LIMITS.motion.max_linear_speed * factor,
        )
        with pytest.raises(AdapterError, match="latérale"):
            assert_speed_within_limits(plan, LIMITS)

    def test_an_over_limit_angular_speed_is_refused(self):
        plan = MotionPlan(
            linear_speed_mps=0.0,
            angular_speed_rps=LIMITS.motion.max_angular_speed * 2,
            nominal_duration_s=1.0,
            timeout_s=2.0,
        )
        with pytest.raises(AdapterError, match="angulaire"):
            assert_speed_within_limits(plan, LIMITS)


class TestTimeout:
    def test_the_margin_is_applied(self):
        assert timeout_for(2.0) == pytest.approx(2.0 * MOVE_TIMEOUT_MARGIN + 1.0)

    def test_the_timeout_is_always_positive(self):
        assert timeout_for(0.0) > 0


class TestGeometry:
    def test_distance_is_euclidean(self):
        # (0,0) -> (3,4) : 5 m, donc 500 cm.
        assert travelled_distance_cm((0.0, 0.0), (3.0, 4.0)) == pytest.approx(500.0)

    def test_the_angular_difference_takes_the_short_way(self):
        # Sans cela, 179° -> -179° donnerait 358° au lieu de 2°.
        import math

        a = math.radians(179.0)
        b = math.radians(-179.0)
        assert shortest_angular_difference_deg(a, b) == pytest.approx(2.0, abs=1e-6)

    def test_identical_caps_give_no_difference(self):
        import math

        angle = math.radians(42.0)
        assert shortest_angular_difference_deg(angle, angle) == pytest.approx(0.0)


class TestTolerances:
    def test_the_documented_tolerances_are_unchanged(self):
        # 5 cm et 8° sont les valeurs retenues pour la campagne physique. Les
        # changer exige de revalider le robot (docs/ROBOT_SETUP.md §12).
        assert POSITION_TOLERANCE_CM == 5.0
        assert YAW_TOLERANCE_DEG == 8.0