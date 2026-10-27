"""Moteur d'exécution : ordre, boucles, conditions, arrêt, sécurité.

Ces tests vérifient le comportement observable : l'ordre des instructions
publiées, le respect d'un arrêt demandé, et le refus de tout mouvement quand
une condition ne peut pas être décidée.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.base import (  # noqa: E402
    AdapterError,
    CommandOutcome,
    Posture,
    RobotAdapter,
    RobotState,
    SafetyInterrupt,
    Status,
    StopSignal,
)
from go2_service.adapters.motion import plan_command  # noqa: E402
from go2_service.adapters.simulated import SimulatedAdapter  # noqa: E402
from go2_service.config import load_limits  # noqa: E402
from go2_service.execution import (  # noqa: E402
    FINISH_COMPLETED,
    FINISH_ERROR,
    FINISH_SAFETY,
    FINISH_STOPPED,
    ConcurrentExecutionError,
    ExecutionEngine,
)
from go2_service.main import ServiceState  # noqa: E402
from go2_service.safety import SafetyWatchdog  # noqa: E402
from go2_service.interpreter import ProgramError, RobotTruth  # noqa: E402
from go2_service.program import parse_program  # noqa: E402
from go2_service.validation import (  # noqa: E402
    ALWAYS_AVAILABLE,
    Capability,
    CommandKind,
    RobotCommand,
)

LIMITS = load_limits()


class FakeAdapter:
    """Adaptateur de test : enregistre ce qu'il reçoit, n'exécute rien."""

    name = "fake"
    physical_commands_enabled = False

    def __init__(
        self,
        *,
        posture=Posture.STAND,
        battery=80.0,
        clearance: float | None = None,
    ) -> None:
        self.executed: list[RobotCommand] = []
        self.stop_calls = 0
        self.prepare_calls = 0
        self.fail_on: RobotCommand | None = None
        self.outcome = "exact"
        self.connected = True
        #: Distance libre annoncée pour chaque direction. `None` = pas de lidar.
        self.clearance = clearance
        self.clearance_directions: list[str] = []
        self._posture = posture
        self._battery = battery
        self.state = RobotState.IDLE

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def prepare_run(self) -> None:
        self.prepare_calls += 1
        self._posture = Posture.STAND

    async def get_status(self) -> Status:
        return Status(
            connected=self.connected,
            state=self.state,
            capabilities=ALWAYS_AVAILABLE,
            position_m=(0.0, 0.0, 0.0),
            yaw_rad=0.0,
            battery_percent=self._battery,
            posture=self._posture,
        )

    async def execute_command(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        self.executed.append(command)
        if self.fail_on is not None and command.kind is self.fail_on.kind:
            return CommandOutcome(index=index, outcome="failed", detail="refusé")
        return CommandOutcome(index=index, outcome=self.outcome)

    async def request_stop(self) -> None:
        self.stop_calls += 1

    async def camera_frame(self) -> bytes | None:
        return None

    async def lidar_points(self) -> list[list[float]] | None:
        return None

    async def lidar_volume(self) -> dict[str, Any] | None:
        return None

    async def clearance_m(self, direction: str) -> float | None:
        self.clearance_directions.append(direction)
        return self.clearance

    async def enter_standby(self) -> None:
        self._posture = Posture.LIE_DOWN

    async def exit_standby(self) -> None:
        self._posture = Posture.STAND

    @property
    def lidar_active(self) -> bool:
        return True

    async def set_lidar_switch(self, on: bool) -> None:
        pass

    async def enter_crouch_mode(self) -> None:
        pass

    async def exit_crouch_mode(self) -> None:
        pass

    @property
    def crouch_mode_active(self) -> bool:
        return False

    async def enter_autonomous_mode(self) -> None:
        pass

    async def exit_autonomous_mode(self) -> None:
        pass

    def supports(self, capability: Capability) -> bool:
        return capability in ALWAYS_AVAILABLE


def kinds(adapter: FakeAdapter) -> list[str]:
    return [command.kind.value for command in adapter.executed]


def run(engine: ExecutionEngine, program: dict, run_id: str = "run-1"):
    async def collect():
        return [event async for event in engine.execute_program(program, run_id)]

    return asyncio.run(collect())


# ---------------------------------------------------------------------------
# Programme de référence : exactement l'exemple du cahier des charges
# ---------------------------------------------------------------------------

SIMPLE_PLAN = {
    "statements": [
        {"kind": "move", "direction": "forward", "seconds": 2},
        {"kind": "turn", "direction": "left", "degrees": 90},
        {"kind": "move", "direction": "forward", "seconds": 2},
        {"kind": "stop_move"},
    ]
}


class TestSimplePlan:
    def test_runs_the_reference_plan_in_order(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(engine, parse_program(SIMPLE_PLAN))

        assert kinds(adapter) == [
            "move_forward",
            "turn_left",
            "move_forward",
            "stop",
        ]
        assert events[-1].reason == FINISH_COMPLETED

    def test_always_stops_the_robot_at_the_end(self):
        # Aucune consigne de mouvement ne doit survivre à la fin du programme.
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        run(engine, parse_program(SIMPLE_PLAN))
        assert adapter.stop_calls >= 1

    def test_the_robot_is_put_on_its_legs_before_the_first_order(self):
        # Le robot doit être sur ses quatre pattes avant le premier ordre :
        # s'il est resté assis, il se relève tout seul.
        adapter = FakeAdapter(posture=Posture.SIT)
        engine = ExecutionEngine(adapter, LIMITS)
        run(engine, parse_program(SIMPLE_PLAN))
        assert adapter.prepare_calls == 1

    def test_the_heart_gesture_becomes_a_physical_command(self):
        # Le « coeur » est un geste du SDK (`FingerHeart`) : il doit
        # atteindre le robot, pas rester dans le service.
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        run(engine, parse_program({"statements": [{"kind": "gesture", "gesture": "heart"}]}))
        assert kinds(adapter) == ["finger_heart"]

    def test_the_salute_and_stretch_gestures_reach_the_robot(self):
        # `Hello` et `Stretch` sont deux commandes officielles du SDK. Le
        # service doit les traduire en commandes physiques distinctes, sans
        # les confondre avec le cœur ou le saut.
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        run(
            engine,
            parse_program(
                {
                    "statements": [
                        {"kind": "gesture", "gesture": "salute"},
                        {"kind": "gesture", "gesture": "stretch"},
                    ]
                }
            ),
        )
        assert kinds(adapter) == ["salute", "stretch"]

    def test_the_speed_is_chosen_by_the_service(self):
        # L'enfant ne saisit pas de vitesse : c'est une limite de sécurité,
        # elle ne peut pas être dépassée par une saisie.
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        run(engine, parse_program(SIMPLE_PLAN))
        assert adapter.executed[0].speed == pytest.approx(LIMITS.motion.max_linear_speed)

    def test_the_rotation_carries_its_measured_target(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        run(engine, parse_program(SIMPLE_PLAN))
        assert adapter.executed[1].angle_deg == pytest.approx(90.0)


class TestObstacleClearance:
    """La carte du lidar décide si une translation a la place de se faire."""

    def test_too_little_room_skips_only_that_action(self):
        # 0,5 m libres devant : une avance de 5 s (1,5 m) ne tient pas.
        # Le geste qui suit doit quand même être exécuté.
        adapter = FakeAdapter(clearance=0.5)
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(
            engine,
            parse_program(
                {
                    "statements": [
                        {"kind": "move", "direction": "forward", "seconds": 5},
                        {"kind": "gesture", "gesture": "salute"},
                    ]
                }
            ),
        )

        assert kinds(adapter) == ["salute"]
        assert adapter.clearance_directions == ["forward"]
        blocked = [
            event
            for event in events
            if event.type == "step_finished" and event.outcome == "blocked"
        ]
        assert len(blocked) == 1
        assert blocked[0].index == 0
        assert "Pas assez de place devant" in (blocked[0].message or "")
        assert "0,5 m" in (blocked[0].message or "")
        assert events[-1].reason == FINISH_COMPLETED

    def test_a_blocked_step_is_not_announced_as_completed(self):
        adapter = FakeAdapter(clearance=0.1)
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(
            engine,
            parse_program(
                {"statements": [{"kind": "move", "direction": "forward", "seconds": 1}]}
            ),
        )

        completed = [e for e in events if e.type == "step_completed"]
        assert completed == []
        assert events[-1].reason == FINISH_COMPLETED

    def test_enough_room_lets_the_move_run(self):
        adapter = FakeAdapter(clearance=10.0)
        engine = ExecutionEngine(adapter, LIMITS)
        run(
            engine,
            parse_program(
                {"statements": [{"kind": "move", "direction": "forward", "seconds": 1}]}
            ),
        )

        assert kinds(adapter) == ["move_forward"]

    def test_without_measurement_the_move_is_not_blocked(self):
        # Simulateur, ou carte absente : on ne peut ni affirmer un mur, ni
        # affirmer que la voie est libre. Le déplacement reste possible.
        adapter = FakeAdapter(clearance=None)
        engine = ExecutionEngine(adapter, LIMITS)
        run(
            engine,
            parse_program(
                {"statements": [{"kind": "move", "direction": "forward", "seconds": 1}]}
            ),
        )

        assert kinds(adapter) == ["move_forward"]

    def test_each_direction_is_checked_with_its_own_name(self):
        adapter = FakeAdapter(clearance=10.0)
        engine = ExecutionEngine(adapter, LIMITS)
        run(
            engine,
            parse_program(
                {
                    "statements": [
                        {"kind": "move", "direction": "forward", "seconds": 1},
                        {"kind": "move", "direction": "backward", "seconds": 1},
                        {"kind": "move", "direction": "left", "seconds": 1},
                        {"kind": "move", "direction": "right", "seconds": 1},
                    ]
                }
            ),
        )

        assert adapter.clearance_directions == [
            "forward",
            "backward",
            "left",
            "right",
        ]
        assert kinds(adapter) == [
            "move_forward",
            "move_backward",
            "move_left",
            "move_right",
        ]

    def test_a_rotation_is_not_checked(self):
        # Tourner sur place ne translate pas le chien vers un mur.
        adapter = FakeAdapter(clearance=0.0)
        engine = ExecutionEngine(adapter, LIMITS)
        run(
            engine,
            parse_program(
                {"statements": [{"kind": "turn", "direction": "left", "degrees": 90}]}
            ),
        )

        assert adapter.clearance_directions == []
        assert kinds(adapter) == ["turn_left"]


class TestRepeat:
    def test_repeats_the_body(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "repeat",
                        "times": 5,
                        "body": [
                            {"kind": "move", "direction": "forward", "seconds": 1}
                        ],
                    }
                ]
            }
        )
        run(engine, program)
        assert kinds(adapter) == ["move_forward"] * 5

    def test_expands_nested_repeats(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "repeat",
                        "times": 3,
                        "body": [
                            {
                                "kind": "repeat",
                                "times": 2,
                                "body": [
                                    {
                                        "kind": "move",
                                        "direction": "forward",
                                        "seconds": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        run(engine, program)
        assert len(adapter.executed) == 6


class TestConditions:
    def test_takes_the_first_branch_when_true(self):
        adapter = FakeAdapter(posture=Posture.STAND)
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "if",
                        "condition": "posture_stand",
                        "then": [{"kind": "move", "direction": "forward", "seconds": 1}],
                        "otherwise": [{"kind": "move", "direction": "backward", "seconds": 1}],
                    }
                ]
            }
        )
        run(engine, program)
        assert kinds(adapter) == ["move_forward"]

    def test_takes_the_second_branch_when_false(self):
        adapter = FakeAdapter(posture=Posture.SIT)
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "if",
                        "condition": "posture_stand",
                        "then": [{"kind": "move", "direction": "forward", "seconds": 1}],
                        "otherwise": [{"kind": "move", "direction": "backward", "seconds": 1}],
                    }
                ]
            }
        )
        run(engine, program)
        assert kinds(adapter) == ["move_backward"]

    def test_battery_condition_reads_the_measured_value(self):
        low = FakeAdapter(battery=10.0)
        engine = ExecutionEngine(low, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "if",
                        "condition": "battery_low",
                        "then": [{"kind": "stop_move"}],
                        "otherwise": [{"kind": "move", "direction": "forward", "seconds": 1}],
                    }
                ]
            }
        )
        run(engine, program)
        assert kinds(low) == ["stop"]

    def test_refuses_to_guess_when_the_measure_is_missing(self):
        # Batterie non lue : le programme s'arrête et le dit. Supposer
        # « batterie correcte » ferait avancer le robot sans que personne ne
        # puisse l'expliquer ensuite.
        adapter = FakeAdapter()
        adapter._battery = None  # noqa: SLF001
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "if",
                        "condition": "battery_low",
                        "then": [{"kind": "stop_move"}],
                        "otherwise": [{"kind": "move", "direction": "forward", "seconds": 1}],
                    }
                ]
            }
        )
        events = run(engine, program)
        assert adapter.executed == []
        assert any(event.type == "error" for event in events)
        assert events[-1].reason == FINISH_ERROR

    def test_a_condition_without_a_branch_does_nothing_but_continue(self):
        adapter = FakeAdapter(posture=Posture.SIT)
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {
                        "kind": "if",
                        "condition": "posture_stand",
                        "then": [{"kind": "stop_move"}],
                    },
                    {"kind": "wait", "seconds": 1},
                ]
            }
        )
        events = run(engine, program)
        assert kinds(adapter) == ["wait"]
        assert events[-1].reason == FINISH_COMPLETED


class TestStopProgram:
    def test_interrups_the_remaining_plan(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        program = parse_program(
            {
                "statements": [
                    {"kind": "move", "direction": "forward", "seconds": 1},
                    {"kind": "stop_program"},
                    {"kind": "move", "direction": "forward", "seconds": 1},
                ]
            }
        )
        run(engine, program)
        assert kinds(adapter) == ["move_forward"]

    def test_stops_the_robot_anyway(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        run(engine, parse_program({"statements": [{"kind": "stop_program"}]}))
        assert adapter.stop_calls >= 1


class TestSafety:
    def test_concurrent_executions_are_refused(self):
        from go2_service.execution import ActiveExecution

        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        engine._active = ActiveExecution(run_id="autre")  # noqa: SLF001
        with pytest.raises(ConcurrentExecutionError):
            run(engine, parse_program(SIMPLE_PLAN))

    def test_a_stop_requested_mid_run_is_honoured(self):
        adapter = FakeAdapter()
        adapter.outcome = "stopped"
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(engine, parse_program(SIMPLE_PLAN))
        assert events[-1].reason == FINISH_STOPPED
        # Le robot n'a exécuté que la première instruction.
        assert len(adapter.executed) == 1

    def test_a_failed_instruction_ends_the_program(self):
        adapter = FakeAdapter()
        adapter.fail_on = RobotCommand(kind=CommandKind.MOVE_FORWARD)
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(engine, parse_program(SIMPLE_PLAN))
        assert events[-1].reason == FINISH_ERROR
        # Rien après l'échec.
        assert kinds(adapter) == ["move_forward"]

    def test_an_over_long_expanded_plan_is_refused_before_any_movement(self):
        adapter = FakeAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        # 20 répétitions autorisées, mais un corps qui dépasse déjà le cumul.
        body = [{"kind": "wait", "seconds": 5}] * 30
        program = parse_program(
            {"statements": [{"kind": "repeat", "times": 20, "body": body}]}
        )
        events = run(engine, program)
        assert adapter.executed == []
        assert any(event.type == "error" for event in events)

    def test_the_watchdog_still_stops_the_robot_on_an_exception(self):
        class Exploding(FakeAdapter):
            async def execute_command(self, command, index, should_stop):
                raise RuntimeError("panne")

        adapter = Exploding()
        engine = ExecutionEngine(adapter, LIMITS)

        async def collect():
            return [e async for e in engine.execute_program(parse_program(SIMPLE_PLAN), "r")]

        with pytest.raises(RuntimeError):
            asyncio.run(collect())
        # L'arrêt a bien été demandé malgré l'exception.
        assert adapter.stop_calls >= 1

    def test_un_arret_de_securite_termine_le_programme_en_safety(self):
        # L'adaptateur a détecté un portage et a déjà envoyé `StopMove`. Le
        # moteur doit arrêter le programme avec la raison « safety » et ne
        # jamais enchaîner sur l'instruction suivante.
        class SafetyAdapter(FakeAdapter):
            async def execute_command(self, command, index, should_stop):
                self.executed.append(command)
                raise SafetyInterrupt("Le robot a été soulevé.")

        adapter = SafetyAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(engine, parse_program(SIMPLE_PLAN))

        assert events[-1].reason == FINISH_SAFETY
        assert len(adapter.executed) == 1
        assert adapter.stop_calls >= 1
        assert any(
            event.type == "step_finished" and event.outcome == "stopped"
            for event in events
        )

    def test_un_arret_de_securite_pendant_la_preparation_ne_bouge_pas(self):
        class SafetyPrepare(FakeAdapter):
            async def prepare_run(self) -> None:
                raise SafetyInterrupt("Le robot n’a plus d’appui au sol.")

        adapter = SafetyPrepare()
        engine = ExecutionEngine(adapter, LIMITS)
        events = run(engine, parse_program(SIMPLE_PLAN))

        assert events[-1].reason == FINISH_SAFETY
        assert adapter.executed == []
        assert adapter.stop_calls >= 1

    def test_le_chien_de_garde_termine_le_programme_sur_un_verrouillage(self):
        from go2_service.execution import ActiveExecution

        class SafetyAdapter(FakeAdapter):
            safety_stop_reason = "Le robot a été soulevé : il s’est arrêté."

        adapter = SafetyAdapter()
        engine = ExecutionEngine(adapter, LIMITS)
        engine._active = ActiveExecution(run_id="run-safety")  # noqa: SLF001
        chien = SafetyWatchdog(engine, adapter, LIMITS)

        resultat = chien.tick()

        assert resultat.triggered is True
        assert resultat.reason == adapter.safety_stop_reason
        assert engine._active.stop_signal.reason == FINISH_SAFETY  # noqa: SLF001
        assert chien.trips == 1

    async def test_le_chien_de_garde_est_relance_apres_branchement(self):
        # `adopt_robot_adapter` reconstruit le moteur ET le chien de garde.
        # Sans redémarrage explicite de ce dernier, plus aucun bail n'était
        # surveillé après un branchement réel.
        limits = load_limits()
        simulation = SimulatedAdapter(limits)
        await simulation.connect()
        etat = ServiceState(limits=limits, adapter=simulation)
        await etat.watchdog.start()
        premier = etat.watchdog

        try:
            # Un ancien réglage « sécurité coupée » ne doit jamais survivre à
            # un nouveau branchement.
            simulation.obstacle_safety_enabled = False
            await etat.adopt_robot_adapter(simulation)
            assert premier.running is False
            assert etat.watchdog.running is True
            assert etat.mode == "real"
            assert etat.obstacle_safety_enabled is True
            assert simulation.obstacle_safety_enabled is True

            etat.set_obstacle_safety(False)
            await etat.release_robot_adapter()
            assert etat.mode == "simulation"
            assert etat.watchdog.running is True
            assert etat.obstacle_safety_enabled is True
        finally:
            await etat.watchdog.stop()


class TestInterpreterBounds:
    def test_a_duration_is_clamped_to_the_service_limits(self):
        # Le service ne doit jamais publier une durée hors limites, même si
        # `limits` était plus permissif que la validation.
        from go2_service.interpreter import Interpreter
        from go2_service.program import parse_statement

        interpreter = Interpreter(LIMITS, RobotTruth(posture="stand"))
        command = interpreter.lower(parse_statement({"kind": "wait", "seconds": 9999}))
        assert command.duration_s <= LIMITS.timing.max_wait_seconds

    def test_an_unreachable_condition_is_an_error_not_a_guess(self):
        from go2_service.interpreter import Interpreter

        interpreter = Interpreter(LIMITS, RobotTruth())
        with pytest.raises(ProgramError):
            interpreter.run(parse_program(
                {"statements": [
                    {
                        "kind": "if",
                        "condition": "posture_stand",
                        "then": [],
                        "otherwise": [],
                    }
                ]}
            ))


class TestMotionPlan:
    def test_a_lateral_move_uses_the_lateral_channel(self):
        command = RobotCommand(kind=CommandKind.MOVE_LEFT, speed=0.2, duration_s=2)
        plan = plan_command(command, LIMITS)
        assert plan is not None
        assert plan.lateral_speed_mps == pytest.approx(0.2)
        assert plan.linear_speed_mps == pytest.approx(0.0)

    def test_a_backward_move_is_signed(self):
        command = RobotCommand(kind=CommandKind.MOVE_BACKWARD, speed=0.2, duration_s=2)
        plan = plan_command(command, LIMITS)
        assert plan is not None
        assert plan.linear_speed_mps < 0

    def test_a_posture_has_no_motion_plan(self):
        assert plan_command(RobotCommand(kind=CommandKind.BALANCE), LIMITS) is None

    def test_the_plan_refuses_an_over_limit_speed_rather_than_silently_clamping(self):
        # L'interpréteur borne déjà les valeurs. Si quelque chose en amont
        # produisait une vitesse excessive, l'adaptateur doit REFUSER
        # bruyamment : brider en silence ferait croire que la consigne demandée
        # a été honorée.
        for kind in (CommandKind.MOVE_LEFT, CommandKind.MOVE_RIGHT):
            command = RobotCommand(
                kind=kind, speed=LIMITS.motion.max_linear_speed * 10, duration_s=1
            )
            with pytest.raises(AdapterError, match="latérale"):
                plan_command(command, LIMITS)

    def test_a_normal_speed_produces_a_plan_within_the_limits(self):
        for kind in (CommandKind.MOVE_LEFT, CommandKind.MOVE_RIGHT,
                     CommandKind.TURN_LEFT, CommandKind.TURN_RIGHT):
            command = RobotCommand(
                kind=kind,
                speed=LIMITS.motion.max_linear_speed,
                duration_s=1,
                angle_deg=90,
            )
            plan = plan_command(command, LIMITS)
            assert plan is not None
            assert abs(plan.linear_speed_mps) <= LIMITS.motion.max_linear_speed + 1e-9
            assert abs(plan.lateral_speed_mps) <= LIMITS.motion.max_linear_speed + 1e-9
            assert abs(plan.angular_speed_rps) <= LIMITS.motion.max_angular_speed + 1e-9


class TestAdapterContract:
    def test_the_fake_adapter_satisfies_the_protocol(self):
        assert isinstance(FakeAdapter(), RobotAdapter)

    def test_physical_commands_stay_disabled(self):
        # Tant que le robot n'a pas été validé physiquement, le mode réel
        # doit rester refusé. `test_safety_adapters.py` le vérifie côté SDK.
        assert FakeAdapter.physical_commands_enabled is False