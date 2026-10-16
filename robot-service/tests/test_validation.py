"""Tests de la configuration partagée et de la validation autoritaire."""

from __future__ import annotations

import json

import pytest

from go2_service.config import ConfigurationError, load_limits
from go2_service.validation import (
    Capability,
    CommandKind,
    CommandValidationError,
    parse_command,
    parse_program,
    validate_program,
)


@pytest.fixture(scope="module")
def limits():
    return load_limits()


ALL_CAPABILITIES = frozenset(Capability)


# --------------------------------------------------------------------------
# Configuration partagée
# --------------------------------------------------------------------------


class TestConfiguration:
    def test_shared_file_is_readable(self, limits):
        """La même source de vérité alimente le frontend et le service."""
        assert limits.motion.max_linear_speed > 0
        assert limits.motion.max_angular_speed > 0
        assert limits.program.max_total_steps > 0
        assert limits.safety.lease_timeout_ms > 0

    def test_lease_is_shorter_than_program_duration(self, limits):
        """Un bail plus long que le programme ne protégerait de rien."""
        assert limits.safety.lease_timeout_ms < limits.program.max_program_seconds * 1000

    def test_heartbeat_faster_than_lease(self, limits):
        assert limits.safety.heartbeat_interval_ms < limits.safety.lease_timeout_ms

    def test_motion_limits_are_positive_and_ordered(self, limits):
        m = limits.motion
        assert 0 < m.min_distance_per_step_cm <= m.max_distance_per_step_cm
        assert 0 < m.min_angle_per_step_deg <= m.max_angle_per_step_deg
        assert 0 < m.max_linear_speed <= 1.0, "vitesse ligneuse Aberrante"
        assert 0 < m.max_angular_speed <= 2.0, "vitesse angulaire Aberrante"


# --------------------------------------------------------------------------
# Analyse des commandes
# --------------------------------------------------------------------------


class TestParseCommand:
    def test_accepts_valid_commands(self):
        assert parse_command({"kind": "move_forward", "distanceCm": 50}).kind is (
            CommandKind.MOVE_FORWARD
        )
        assert parse_command({"kind": "turn_left", "angleDeg": 90}).angle_deg == 90
        assert parse_command({"kind": "wait", "seconds": 3}).seconds == 3
        assert parse_command({"kind": "stop"}).kind is CommandKind.STOP

    def test_rejects_unknown_kind(self):
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "self_destruct"})

    def test_rejects_missing_kind(self):
        with pytest.raises(CommandValidationError):
            parse_command({"distanceCm": 50})

    def test_rejects_missing_parameter(self):
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "move_forward"})
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "wait"})

    @pytest.mark.parametrize("bad", ["50", None, True, [50], {}])
    def test_rejects_non_numeric_parameter(self, bad):
        """Un booléen est un int en Python : il doit être refusé explicitement."""
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "move_forward", "distanceCm": bad})

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_parameter(self, bad):
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "move_forward", "distanceCm": bad})

    @pytest.mark.parametrize("bad", [None, "avancer", 42, [1, 2], {"kind": {}}])
    def test_rejects_non_object(self, bad):
        with pytest.raises(CommandValidationError):
            parse_command(bad)

    def test_uses_absolute_value(self):
        assert parse_command({"kind": "move_backward", "distanceCm": -50}).distance_cm == 50

    def test_rejects_program_that_is_not_a_list(self):
        with pytest.raises(CommandValidationError):
            parse_program({"kind": "stop"})


# --------------------------------------------------------------------------
# Validation autoritaire
# --------------------------------------------------------------------------


class TestValidateProgram:
    def test_accepts_a_sensible_program(self, limits):
        commands = parse_program(
            [
                {"kind": "stand_up"},
                {"kind": "move_forward", "distanceCm": 50},
                {"kind": "turn_left", "angleDeg": 90},
                {"kind": "wait", "seconds": 1},
            ]
        )
        report = validate_program(commands, limits, ALL_CAPABILITIES)
        assert report.valid, report.issues
        assert report.total_distance_cm == 50
        assert report.total_angle_deg == 90

    def test_rejects_empty_program(self, limits):
        report = validate_program([], limits, ALL_CAPABILITIES)
        assert not report.valid

    def test_rejects_step_below_minimum_distance(self, limits):
        commands = parse_program([{"kind": "move_forward", "distanceCm": 1}])
        report = validate_program(commands, limits, ALL_CAPABILITIES)
        assert not report.valid
        assert "cm" in report.first_message()

    def test_rejects_step_above_maximum_distance(self, limits):
        commands = parse_program(
            [{"kind": "move_forward", "distanceCm": limits.motion.max_distance_per_step_cm + 1}]
        )
        assert not validate_program(commands, limits, ALL_CAPABILITIES).valid

    def test_accepts_exact_bounds(self, limits):
        commands = parse_program(
            [
                {
                    "kind": "move_forward",
                    "distanceCm": limits.motion.min_distance_per_step_cm,
                },
                {
                    "kind": "turn_left",
                    "angleDeg": limits.motion.max_angle_per_step_deg,
                },
            ]
        )
        assert validate_program(commands, limits, ALL_CAPABILITIES).valid

    def test_rejects_wait_out_of_range(self, limits):
        too_short = parse_program([{"kind": "wait", "seconds": 0}])
        too_long = parse_program(
            [{"kind": "wait", "seconds": limits.timing.max_wait_seconds + 1}]
        )
        assert not validate_program(too_short, limits, ALL_CAPABILITIES).valid
        assert not validate_program(too_long, limits, ALL_CAPABILITIES).valid

    def test_rejects_too_many_steps(self, limits):
        commands = parse_program([{"kind": "stop"}] * (limits.program.max_total_steps + 1))
        report = validate_program(commands, limits, ALL_CAPABILITIES)
        assert not report.valid

    def test_rejects_excessive_total_distance(self, limits):
        step = limits.motion.max_distance_per_step_cm
        count = int(limits.program.max_total_distance_cm // step) + 2
        commands = parse_program([{"kind": "move_forward", "distanceCm": step}] * count)
        report = validate_program(commands, limits, ALL_CAPABILITIES)
        assert not report.valid
        assert any("cm" in issue.message for issue in report.issues)

    def test_rejects_excessive_duration(self, limits):
        count = limits.program.max_total_steps
        commands = parse_program(
            [{"kind": "wait", "seconds": limits.timing.max_wait_seconds}] * count
        )
        report = validate_program(commands, limits, ALL_CAPABILITIES)
        assert not report.valid

    def test_rejects_unavailable_capability(self, limits):
        commands = parse_program([{"kind": "move_forward", "distanceCm": 50}])
        report = validate_program(commands, limits, frozenset({Capability.WAIT}))
        assert not report.valid
        assert any("n’est pas disponible" in i.message for i in report.issues)

    def test_issue_carries_index_for_localisation(self, limits):
        commands = parse_program(
            [
                {"kind": "move_forward", "distanceCm": 50},
                {"kind": "move_forward", "distanceCm": 9999},
            ]
        )
        report = validate_program(commands, limits, ALL_CAPABILITIES)
        assert not report.valid
        assert any(issue.index == 1 for issue in report.issues)


class TestSharedFileIntegrity:
    def test_shared_json_is_valid_and_parsable(self):
        """Détecte une corruption du fichier de vérité partagé."""
        from go2_service.config import _LIMITS_PATH

        data = json.loads(_LIMITS_PATH.read_text(encoding="utf-8"))
        assert data["version"] == 1
        for section in ("motion", "timing", "program", "safety", "service"):
            assert section in data