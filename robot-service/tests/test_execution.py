"""Tests du moteur d'exécution, de l'adaptateur simulé et de la sécurité.

Le simulateur est utilisé pour TOUS ces tests : aucun test automatique ne
déclenche de mouvement physique. Voir docs/TESTS.md.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from go2_service.adapters.base import AdapterError, StopSignal
from go2_service.adapters.motion import (
    assert_speed_within_limits,
    nominal_duration_for_angle,
    nominal_duration_for_distance,
    plan_command,
    shortest_angular_difference_deg,
    timeout_for,
    travelled_distance_cm,
)
from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.config import load_limits
from go2_service.execution import (
    FINISH_COMPLETED,
    FINISH_ERROR,
    FINISH_SAFETY,
    FINISH_STOPPED,
    ConcurrentExecutionError,
    ExecutionEngine,
)
from go2_service.safety import SafetyWatchdog
from go2_service.validation import CommandKind, RobotCommand

# Le simulateur avance le temps simulé `SIM_SPEEDUP` fois plus vite que le
# temps réel, afin que les tests restent rapides. Un programme de 200 cm
# (≈ 17 s de délai de sécurité simulé) se déroule alors en ~0.4 s réelle.
# La logique testée est par ailleurs identique à la production.
SIM_SPEEDUP = 50.0


@pytest.fixture
def limits():
    return load_limits()


def make_adapter(limits, **kwargs) -> SimulatedAdapter:
    kwargs.setdefault("tick_multiplier", SIM_SPEEDUP)
    return SimulatedAdapter(limits, **kwargs)


def cmd(kind: CommandKind, **kwargs) -> RobotCommand:
    return RobotCommand(kind=kind, **kwargs)


async def collect(engine, commands):
    """Exécute et renvoie la liste d'événements."""
    run_id = engine.new_run_id()
    return [event async for event in engine.execute(commands, run_id)]


# --------------------------------------------------------------------------
# Planification de mouvement
# --------------------------------------------------------------------------


class TestMotionPlanning:
    def test_distance_duration_matches_speed(self, limits):
        speed = limits.motion.max_linear_speed
        # 50 cm = 0.5 m
        assert nominal_duration_for_distance(50, speed) == pytest.approx(0.5 / speed)

    def test_angle_duration_matches_speed(self, limits):
        import math

        speed = limits.motion.max_angular_speed
        expected = math.radians(90) / speed
        assert nominal_duration_for_angle(90, speed) == pytest.approx(expected)

    def test_plan_uses_max_speed(self, limits):
        plan = plan_command(cmd(CommandKind.MOVE_FORWARD, distance_cm=100), limits)
        assert plan is not None
        assert plan.linear_speed_mps == limits.motion.max_linear_speed

    def test_backward_plan_is_negative(self, limits):
        plan = plan_command(cmd(CommandKind.MOVE_BACKWARD, distance_cm=100), limits)
        assert plan is not None and plan.linear_speed_mps < 0

    def test_turn_plan_has_no_linear_speed(self, limits):
        for kind in (CommandKind.TURN_LEFT, CommandKind.TURN_RIGHT):
            plan = plan_command(cmd(kind, angle_deg=90), limits)
            assert plan is not None
            assert plan.linear_speed_mps == 0.0

    def test_turn_direction_sign(self, limits):
        left = plan_command(cmd(CommandKind.TURN_LEFT, angle_deg=90), limits)
        right = plan_command(cmd(CommandKind.TURN_RIGHT, angle_deg=90), limits)
        assert left is not None and right is not None
        assert left.angular_speed_rps > 0
        assert right.angular_speed_rps < 0

    def test_non_motion_commands_have_no_plan(self, limits):
        for kind in (CommandKind.WAIT, CommandKind.STAND_UP, CommandKind.SIT_DOWN, CommandKind.STOP):
            assert plan_command(cmd(kind, seconds=1), limits) is None

    def test_timeout_exceeds_nominal_duration(self, limits):
        plan = plan_command(cmd(CommandKind.MOVE_FORWARD, distance_cm=100), limits)
        assert plan is not None
        assert plan.timeout_s > plan.nominal_duration_s

    def test_speed_guard_rejects_excessive_speed(self, limits):
        from go2_service.adapters.base import MotionPlan

        too_fast = MotionPlan(
            linear_speed_mps=limits.motion.max_linear_speed * 2,
            angular_speed_rps=0.0,
            nominal_duration_s=1.0,
            timeout_s=1.0,
        )
        with pytest.raises(AdapterError):
            assert_speed_within_limits(too_fast, limits)

    def test_speed_guard_accepts_limit_speed(self, limits):
        from go2_service.adapters.base import MotionPlan

        at_limit = MotionPlan(
            linear_speed_mps=limits.motion.max_linear_speed,
            angular_speed_rps=limits.motion.max_angular_speed,
            nominal_duration_s=1.0,
            timeout_s=1.0,
        )
        assert_speed_within_limits(at_limit, limits)

    def test_angular_difference_takes_shortest_path(self):
        """179° vers -179° doit valoir 2°, et non 358°."""
        import math

        a = math.radians(179)
        b = math.radians(-179)
        assert shortest_angular_difference_deg(a, b) == pytest.approx(2.0, abs=1e-6)

    def test_travelled_distance(self):
        assert travelled_distance_cm((0.0, 0.0), (1.0, 0.0)) == pytest.approx(100.0)
        assert travelled_distance_cm((0.0, 0.0), (0.0, 0.0)) == 0.0


# --------------------------------------------------------------------------
# Adaptateur simulé
# --------------------------------------------------------------------------


class TestSimulatedAdapter:
    async def test_connect_then_status(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        status = await adapter.get_status()
        assert status.connected
        assert status.state.value == "idle"

    async def test_disconnect_is_reported(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        await adapter.disconnect()
        status = await adapter.get_status()
        assert not status.connected

    async def test_refuses_command_when_disconnected(self, limits):
        adapter = make_adapter(limits)
        # Non connecté : doit refuser, pas improviser.
        with pytest.raises(AdapterError):
            await adapter.execute_command(
                cmd(CommandKind.MOVE_FORWARD, distance_cm=50), 0, StopSignal()
            )

    async def test_forward_reaches_target_with_measured_value(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        outcome = await adapter.execute_command(
            cmd(CommandKind.MOVE_FORWARD, distance_cm=50), 0, StopSignal()
        )
        assert outcome.outcome == "exact"
        # La mesure vient de l'intégration, elle est donc proche de 50 cm.
        assert outcome.measured_distance_cm == pytest.approx(50, abs=6)

    async def test_turn_reaches_target_with_measured_angle(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        outcome = await adapter.execute_command(
            cmd(CommandKind.TURN_LEFT, angle_deg=90), 0, StopSignal()
        )
        assert outcome.outcome == "exact"
        assert outcome.measured_angle_deg == pytest.approx(90, abs=9)

    async def test_measured_value_is_never_the_commanded_one(self, limits):
        """Le résultat doit venir de l'état, pas recopier la consigne.

        Avec une dérive simulée, la valeur mesurée diffère de la consigne.
        """
        adapter = make_adapter(limits, drift_ratio=0.08, seed=7)
        await adapter.connect()
        outcome = await adapter.execute_command(
            cmd(CommandKind.MOVE_FORWARD, distance_cm=100), 0, StopSignal()
        )
        assert outcome.measured_distance_cm != 100.0

    async def test_stuck_robot_times_out_instead_of_claiming_success(self, limits):
        """Un robot bloqué doit finir en délai dépassé, jamais en « réussi »."""
        adapter = make_adapter(limits)
        adapter.simulate_stuck = True
        await adapter.connect()
        outcome = await adapter.execute_command(
            cmd(CommandKind.MOVE_FORWARD, distance_cm=100), 0, StopSignal()
        )
        assert outcome.outcome == "timeout"

    async def test_stop_signal_interrupts_motion(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        signal = StopSignal()
        task = asyncio.create_task(
            adapter.execute_command(
                cmd(CommandKind.MOVE_FORWARD, distance_cm=200), 0, signal
            )
        )
        await asyncio.sleep(0.05)
        signal.request("test")
        outcome = await task
        assert outcome.outcome == "stopped"

    async def test_disconnect_during_motion_raises(self, limits):
        adapter = make_adapter(limits)
        adapter.simulate_disconnect_during_motion = True
        await adapter.connect()
        with pytest.raises(AdapterError):
            await adapter.execute_command(
                cmd(CommandKind.MOVE_FORWARD, distance_cm=200), 0, StopSignal()
            )

    async def test_posture_commands_succeed(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        for kind in (CommandKind.STAND_UP, CommandKind.SIT_DOWN):
            outcome = await adapter.execute_command(cmd(kind), 0, StopSignal())
            assert outcome.outcome == "exact"

    async def test_posture_reports_no_measurement(self, limits):
        """Le SDK ne confirme pas une posture : on ne doit pas inventer."""
        adapter = make_adapter(limits)
        await adapter.connect()
        outcome = await adapter.execute_command(cmd(CommandKind.STAND_UP), 0, StopSignal())
        assert outcome.measured_distance_cm is None
        assert outcome.measured_angle_deg is None


# --------------------------------------------------------------------------
# Moteur d'exécution
# --------------------------------------------------------------------------


class TestExecutionEngine:
    async def test_runs_program_in_order(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)

        events = await collect(
            engine,
            [
                cmd(CommandKind.STAND_UP),
                cmd(CommandKind.WAIT, seconds=0.1),
                cmd(CommandKind.STOP),
            ],
        )
        assert events[-1].type == "execution_finished"
        assert events[-1].reason == FINISH_COMPLETED

        started = [e.index for e in events if e.type == "step_started"]
        assert started == [0, 1, 2]

    async def test_emits_measured_value(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)
        events = await collect(engine, [cmd(CommandKind.MOVE_FORWARD, distance_cm=50)])
        finished = [e for e in events if e.type == "step_finished"]
        assert finished and finished[0].measured is not None
        assert finished[0].outcome == "exact"

    async def test_stop_request_interrupts(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)

        commands = [cmd(CommandKind.MOVE_FORWARD, distance_cm=200) for _ in range(5)]
        run_id = engine.new_run_id()

        events = []
        async for event in engine.execute(commands, run_id):
            events.append(event)
            if event.type == "step_started" and len(events) < 3:
                engine.request_stop()

        assert events[-1].type == "execution_finished"
        assert events[-1].reason == FINISH_STOPPED

    async def test_rejects_concurrent_execution(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)

        commands = [cmd(CommandKind.MOVE_FORWARD, distance_cm=200)] * 4
        run_id = engine.new_run_id()

        collected = []

        async def first():
            async for event in engine.execute(commands, run_id):
                collected.append(event)

        task = asyncio.create_task(first())
        await asyncio.sleep(0.05)

        assert engine.is_running
        with pytest.raises(ConcurrentExecutionError):
            await collect(engine, [cmd(CommandKind.STOP)])

        await task

    async def test_adapter_error_is_reported_as_error(self, limits):
        adapter = make_adapter(limits)
        adapter.fail_next_command = True
        await adapter.connect()
        engine = ExecutionEngine(adapter)

        events = await collect(engine, [cmd(CommandKind.MOVE_FORWARD, distance_cm=50)])
        assert any(e.type == "error" for e in events)
        assert events[-1].reason == FINISH_ERROR

    async def test_engine_always_stops_adapter_at_end(self, limits):
        """Aucune consigne de mouvement ne doit survivre au programme."""
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)

        calls = {"n": 0}
        original = adapter.request_stop

        async def counting_stop():
            calls["n"] += 1
            await original()

        adapter.request_stop = counting_stop

        await collect(engine, [cmd(CommandKind.WAIT, seconds=0.1)])
        assert calls["n"] >= 1

    async def test_engine_recovers_after_error(self, limits):
        """Une exécution échouée ne doit pas rester verrouillée."""
        adapter = make_adapter(limits)
        adapter.fail_next_command = True
        await adapter.connect()
        engine = ExecutionEngine(adapter)

        await collect(engine, [cmd(CommandKind.STOP)])
        assert not engine.is_running

        events = await collect(engine, [cmd(CommandKind.STOP)])
        assert events[-1].reason == FINISH_COMPLETED


# --------------------------------------------------------------------------
# Sécurité : bail et chien de garde
# --------------------------------------------------------------------------


class TestSafetyWatchdog:
    async def test_no_trigger_without_execution(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        watchdog = SafetyWatchdog(ExecutionEngine(adapter), adapter, limits)
        assert watchdog.tick().triggered is False

    async def test_no_trigger_while_heartbeats_arrive(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)
        watchdog = SafetyWatchdog(engine, adapter, limits)

        run_id = engine.new_run_id()
        commands = [cmd(CommandKind.WAIT, seconds=0.3)]

        results = []
        async for event in engine.execute(commands, run_id):
            results.append(event)
            # Simule un frontend vivant : il envoi des battements.
            engine.notify_heartbeat(time.monotonic())
            assert watchdog.tick().triggered is False

        assert results[-1].reason == FINISH_COMPLETED

    async def test_triggers_when_lease_expires(self, limits):
        """Le cas critique : le frontend disparaît pendant un mouvement."""
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)
        watchdog = SafetyWatchdog(engine, adapter, limits)

        run_id = engine.new_run_id()
        commands = [cmd(CommandKind.MOVE_FORWARD, distance_cm=200)]

        async for event in engine.execute(commands, run_id):
            if event.type == "step_started":
                # Aucun battement : on laisse le bail expirer.
                engine.notify_heartbeat(
                    time.monotonic() - (limits.safety.lease_timeout_ms / 1000.0) - 1.0
                )
                result = watchdog.tick()
                assert result.triggered is True
                assert "Bail expiré" in (result.reason or "")

        assert watchdog.trips == 1

    async def test_safety_stop_is_reported_as_safety_reason(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)
        watchdog = SafetyWatchdog(engine, adapter, limits)

        run_id = engine.new_run_id()
        commands = [cmd(CommandKind.MOVE_FORWARD, distance_cm=200)]

        reasons = []
        async for event in engine.execute(commands, run_id):
            if event.type == "step_started":
                watchdog.tick  # pas d'arrêt ici
                engine.request_stop(FINISH_SAFETY)
            if event.type == "execution_finished":
                reasons.append(event.reason)

        assert FINISH_SAFETY in reasons

    async def test_emergency_stop_calls_adapter(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)
        watchdog = SafetyWatchdog(engine, adapter, limits)

        calls = {"n": 0}
        original = adapter.request_stop

        async def counting():
            calls["n"] += 1
            await original()

        adapter.request_stop = counting
        await watchdog.emergency_stop()
        assert calls["n"] == 1

    async def test_heartbeat_age_is_measured(self, limits):
        adapter = make_adapter(limits)
        await adapter.connect()
        engine = ExecutionEngine(adapter)
        assert engine.heartbeat_age(time.monotonic()) is None


class TestStopSignal:
    def test_first_reason_wins(self):
        signal = StopSignal()
        signal.request("bouton")
        signal.request("bail")
        assert signal.reason == "bouton"

    def test_requested_flag(self):
        signal = StopSignal()
        assert not signal.requested
        signal.request()
        assert signal.requested

    def test_reset(self):
        signal = StopSignal()
        signal.request()
        signal.reset()
        assert not signal.requested
        assert signal.reason is None