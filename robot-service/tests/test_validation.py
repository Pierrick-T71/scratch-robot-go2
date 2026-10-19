"""Validation autoritaire : forme des instructions et bornes du programme.

Ces tests sont la DERNIÈRE ligne de défense. Un client modifié, un fichier de
mission bricolé ou une régression du frontend doivent tous se heurter ici.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.config import load_limits  # noqa: E402
from go2_service.program import (  # noqa: E402
    MoveStatement,
    Program,
    count_steps,
    max_seconds,
    parse_program,
    parse_statement,
    validate_structure,
)
from go2_service.validation import (  # noqa: E402
    ALWAYS_AVAILABLE,
    Capability,
    CommandKind,
    CommandValidationError,
    RobotCommand,
    parse_command,
    validate_program,
)

LIMITS = load_limits()


def statement(kind: str, **fields) -> dict:
    return {"kind": kind, **fields}


def movement(seconds: float = 2) -> dict:
    return statement("move", direction="forward", seconds=seconds)


def rotation(degrees: float = 90) -> dict:
    return statement("turn", direction="left", degrees=degrees)


# ---------------------------------------------------------------------------
# Instructions physiques
# ---------------------------------------------------------------------------


class TestParseCommand:
    def test_accepts_a_move(self):
        command = parse_command(
            {"kind": "move_forward", "speed": 0.2, "durationS": 2}
        )
        assert command.kind is CommandKind.MOVE_FORWARD
        assert command.speed == pytest.approx(0.2)
        assert command.duration_s == pytest.approx(2.0)

    def test_accepts_a_rotation_with_its_measured_target(self):
        command = parse_command(
            {"kind": "turn_left", "speed": 0.5, "durationS": 4, "angleDeg": 90}
        )
        assert command.kind is CommandKind.TURN_LEFT
        assert command.angle_deg == pytest.approx(90.0)

    def test_accepts_a_posture(self):
        assert parse_command({"kind": "stand_up"}).kind is CommandKind.STAND_UP
        assert parse_command({"kind": "balance"}).kind is CommandKind.BALANCE

    def test_uses_absolute_value(self):
        command = parse_command({"kind": "move_forward", "speed": -0.2, "durationS": 2})
        assert command.speed == pytest.approx(0.2)

    @pytest.mark.parametrize("raw", [None, [], "move", 42])
    def test_refuses_a_non_object(self, raw):
        with pytest.raises(CommandValidationError):
            parse_command(raw)

    def test_refuses_an_unknown_kind(self):
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "self_destruct"})

    @pytest.mark.parametrize("value", [True, False, "2", None, [], {}])
    def test_refuses_a_boolean_where_a_number_is_expected(self, value):
        # `isinstance(True, int)` est vrai en Python : sans ce refus,
        # `true` passerait pour 1.
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "move_forward", "speed": value, "durationS": 2})

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_refuses_an_impossible_number(self, value):
        with pytest.raises(CommandValidationError):
            parse_command({"kind": "move_forward", "speed": value, "durationS": 2})

    def test_labels_are_readable_french(self):
        assert "Avancer" in RobotCommand(
            kind=CommandKind.MOVE_FORWARD, speed=0.2, duration_s=2
        ).label()
        assert "debout" in RobotCommand(kind=CommandKind.STAND_UP).label()


class TestMotionFlags:
    def test_a_move_is_motion(self):
        assert RobotCommand(kind=CommandKind.MOVE_LEFT, speed=0.2).is_motion
        assert RobotCommand(kind=CommandKind.TURN_RIGHT).is_motion

    def test_a_posture_is_not_motion(self):
        assert not RobotCommand(kind=CommandKind.BALANCE).is_motion


class TestValidateFlatCommands:
    def test_accepts_a_sensible_plan(self):
        commands = [
            RobotCommand(kind=CommandKind.MOVE_FORWARD, speed=0.2, duration_s=2),
            RobotCommand(kind=CommandKind.WAIT, duration_s=1),
        ]
        assert validate_program(commands, LIMITS, ALWAYS_AVAILABLE).valid

    def test_rejects_a_speed_above_the_limit(self):
        command = RobotCommand(
            kind=CommandKind.MOVE_FORWARD, speed=LIMITS.motion.max_linear_speed * 2, duration_s=1
        )
        assert not validate_program([command], LIMITS, ALWAYS_AVAILABLE).valid

    def test_rejects_a_duration_above_the_limit(self):
        command = RobotCommand(
            kind=CommandKind.MOVE_FORWARD,
            speed=0.1,
            duration_s=LIMITS.timing.max_wait_seconds + 1,
        )
        assert not validate_program([command], LIMITS, ALWAYS_AVAILABLE).valid

    def test_rejects_an_unavailable_capability(self):
        command = RobotCommand(kind=CommandKind.MOVE_FORWARD, speed=0.2, duration_s=1)
        report = validate_program([command], LIMITS, frozenset())
        assert not report.valid
        assert "n’est pas disponible" in report.first_message()

    def test_rejects_an_empty_plan(self):
        assert not validate_program([], LIMITS, ALWAYS_AVAILABLE).valid


# ---------------------------------------------------------------------------
# Programme structuré
# ---------------------------------------------------------------------------


class TestParseStatement:
    def test_accepts_a_move(self):
        parsed = parse_statement(movement(3))
        assert isinstance(parsed, MoveStatement)
        assert parsed.seconds == pytest.approx(3.0)

    @pytest.mark.parametrize("direction", ["forward", "backward", "left", "right"])
    def test_accepts_every_direction(self, direction):
        parsed = parse_statement(statement("move", direction=direction, seconds=2))
        assert parsed.direction == direction

    @pytest.mark.parametrize("direction", ["up", "diagonal", "", None])
    def test_refuses_an_unknown_direction(self, direction):
        with pytest.raises(CommandValidationError):
            parse_statement(statement("move", direction=direction, seconds=2))

    def test_refuses_an_unknown_kind(self):
        with pytest.raises(CommandValidationError):
            parse_statement(statement("teleport"))

    def test_refuses_a_non_integer_repeat_count(self):
        # Le nombre de répétitions est une borne structurelle : il doit être
        # connu à la compilation, pas dépendre d'un calcul à l'exécution.
        with pytest.raises(CommandValidationError):
            parse_statement(statement("repeat", times=2.5, body=[]))

    def test_refuses_a_negative_repeat_count(self):
        with pytest.raises(CommandValidationError):
            parse_statement(statement("repeat", times=-1, body=[]))

    @pytest.mark.parametrize("condition", ["obstacle_detected", "battery_ok", "", None])
    def test_refuses_a_condition_that_is_not_implemented(self, condition):
        with pytest.raises(CommandValidationError):
            parse_statement(
                statement(
                    "if",
                    condition=condition,
                    then=[],
                    otherwise=[],
                )
            )

    def test_accepts_the_conditions_that_are_implemented(self):
        for condition in ("posture_stand", "battery_low"):
            parsed = parse_statement(statement("if", condition=condition, then=[]))
            assert parsed.condition == condition

    def test_refuses_a_posture_that_does_not_exist(self):
        with pytest.raises(CommandValidationError):
            parse_statement(statement("posture", posture="backflip"))


class TestParseProgram:
    def test_accepts_a_whole_plan(self):
        program = parse_program(
            {"statements": [movement(2), rotation(90), statement("stop_move")]}
        )
        assert len(program.statements) == 3

    def test_refuses_an_unknown_top_level_field(self):
        # Une version de frontend plus récente ne doit pas pouvoir introduire
        # une instruction non vérifiée.
        with pytest.raises(CommandValidationError):
            parse_program({"statements": [], "turbo": True})

    def test_refuses_a_non_object(self):
        with pytest.raises(CommandValidationError):
            parse_program([movement(2)])

    def test_survives_a_deeply_nested_plan(self):
        # La profondeur est bornée : un programme immense ne doit pas faire
        # tomber Python.
        body: list[dict] = []
        for _ in range(500):
            body = [statement("repeat", times=2, body=body)]
        with pytest.raises(CommandValidationError):
            parse_program({"statements": body})


class TestValidateStructure:
    def test_accepts_a_sensible_plan(self):
        program = parse_program({"statements": [movement(2), rotation(90)]})
        assert validate_structure(program, LIMITS).valid

    def test_rejects_an_empty_plan(self):
        assert not validate_structure(Program(statements=[]), LIMITS).valid

    def test_rejects_a_duration_not_offered_by_the_menus(self):
        # 0,25 s曾经 était saisissable ; ce n'est plus proposé. Un fichier
        # bricolé ne doit pas passer.
        program = parse_program({"statements": [movement(0.25)]})
        report = validate_structure(program, LIMITS)
        assert not report.valid
        assert "pas proposé" in report.first_message()

    def test_rejects_an_angle_not_offered_by_the_menus(self):
        program = parse_program({"statements": [rotation(37)]})
        assert not validate_structure(program, LIMITS).valid

    def test_rejects_a_repeat_count_not_offered(self):
        program = parse_program({"statements": [statement("repeat", times=7, body=[])]})
        assert not validate_structure(program, LIMITS).valid

    def test_rejects_too_many_repeats(self):
        # 10 répétitions × 3 déplacements de 5 s = 150 s, au-delà des 120 s.
        body = [movement(5), movement(5), movement(5)]
        program = parse_program({"statements": [statement("repeat", times=10, body=body)]})
        report = validate_structure(program, LIMITS)
        assert not report.valid
        assert "durerait" in report.first_message()

    def test_rejects_deeply_nested_repeats(self):
        body: list[dict] = [movement(1)]
        for _ in range(LIMITS.program.max_nested_repeat_depth + 2):
            body = [statement("repeat", times=2, body=body)]
        program = parse_program({"statements": body})
        assert not validate_structure(program, LIMITS).valid

    def test_rejects_a_too_long_plan(self):
        program = parse_program(
            {"statements": [movement(1) for _ in range(LIMITS.program.max_total_steps + 10)]}
        )
        assert not validate_structure(program, LIMITS).valid

    def test_carries_the_line_for_localisation(self):
        program = parse_program({"statements": [{"kind": "move", "direction": "forward", "seconds": 0.25, "line": 12345}]})
        report = validate_structure(program, LIMITS)
        assert report.issues[0].line == 12345


class TestStructureCounts:
    def test_count_steps_expands_repeats(self):
        program = parse_program(
            {"statements": [statement("repeat", times=5, body=[movement(1)])]}
        )
        assert count_steps(program.statements) == 5

    def test_count_steps_expands_both_branches(self):
        program = parse_program(
            {
                "statements": [
                    statement(
                        "if",
                        condition="posture_stand",
                        then=[movement(1)],
                        otherwise=[movement(1), rotation(90)],
                    )
                ]
            }
        )
        # 1 (le si) + 1 (alors) + 2 (sinon)
        assert count_steps(program.statements) == 4

    def test_max_seconds_uses_the_longest_branch(self):
        # Pour une condition, on ne sait pas laquelle sera prise : on retient
        # la plus longue, sinon un programme pourrait être refusé à tort.
        program = parse_program(
            {
                "statements": [
                    statement(
                        "if",
                        condition="posture_stand",
                        then=[movement(1)],
                        otherwise=[movement(5)],
                    )
                ]
            }
        )
        assert max_seconds(program.statements) == pytest.approx(5.0)


class TestCapabilities:
    def test_logic_is_always_available(self):
        # Les variables et les messages ne commandent aucun organe : ils
        # s'exécutent dans le service.
        assert Capability.VARIABLE in ALWAYS_AVAILABLE
        assert Capability.BROADCAST in ALWAYS_AVAILABLE

    def test_obstacle_detection_is_not_available_on_a_real_robot(self):
        # Aucune mesure de distance n'a été identifiée dans le SDK officiel.
        assert Capability.SENSOR_OBSTACLE not in ALWAYS_AVAILABLE