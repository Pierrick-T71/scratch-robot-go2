"""Tests du mode de navigation autonome (AutonomousControl et endpoints)."""

import asyncio
import pytest
from fastapi.testclient import TestClient

from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.autonomous import AutonomousControl
from go2_service.config import load_limits
from go2_service.main import create_app


@pytest.fixture
def adapter():
    return SimulatedAdapter(load_limits())


@pytest.fixture
def autonomous(adapter):
    return AutonomousControl(adapter)


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


class TestAutonomousControl:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, autonomous):
        assert not autonomous.active
        ok, msg = await autonomous.start()
        assert ok
        assert msg is None
        assert autonomous.active

        # Idempotent start
        ok, msg = await autonomous.start()
        assert ok
        assert autonomous.active

        await autonomous.stop()
        assert not autonomous.active

        # Idempotent stop
        await autonomous.stop()
        assert not autonomous.active

    @pytest.mark.asyncio
    async def test_avoid_obstacle_and_turn(self, adapter, autonomous):
        await adapter.connect()
        calls = []

        # Mock clearance: forward starts blocked (0.50m), then after pivot becomes clear (2.0m)
        async def mock_clearance(direction):
            if direction == "forward":
                if not calls:
                    return 0.50  # First reading: obstacle ahead!
                return 2.0  # After turn: path is clear!
            if direction == "left":
                return 2.5  # Left is wide open
            if direction == "right":
                return 0.4  # Right is blocked
            return 1.0

        # Spy on manual_velocity
        orig_manual_velocity = adapter.manual_velocity

        def spy_manual_velocity(direction, speed_mps, turn_speed_rps):
            calls.append((direction, speed_mps, turn_speed_rps))
            return orig_manual_velocity(direction, speed_mps, turn_speed_rps)

        adapter.clearance_m = mock_clearance
        adapter.manual_velocity = spy_manual_velocity

        ok, msg = await autonomous.start()
        assert ok
        # Wait enough time for the avoidance maneuver to trigger (0.3s)
        await asyncio.sleep(0.4)
        await autonomous.stop()

        # The robot should have detected obstacle, stopped forward, and turned left (open side)
        turn_calls = [c for c in calls if c[0] == "turn_left"]
        assert len(turn_calls) > 0
        assert turn_calls[0][2] == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_stop_on_dead_end(self, adapter, autonomous):
        await adapter.connect()
        stopped_reasons = []

        async def on_stop(reason):
            stopped_reasons.append(reason)

        autonomous.set_on_stop(on_stop)
        # Mock clearance to be permanently blocked in all directions
        adapter.clearance_m = lambda direction: asyncio.sleep(0, result=0.35)

        ok, msg = await autonomous.start()
        assert ok
        # Wait for the multiple turns to exhaust and stop (approx 4.8s total)
        for _ in range(60):
            if not autonomous.active:
                break
            await asyncio.sleep(0.1)

        assert not autonomous.active
        assert autonomous.last_stop_reason == "Espace bloqué : impossible de trouver une issue après pivot."
        assert "Espace bloqué : impossible de trouver une issue après pivot." in stopped_reasons


class TestAutonomousEndpoints:
    def test_start_toggle_and_stop(self, client):
        # 1. Toggle ON
        resp = client.post("/api/autonomous/toggle")
        assert resp.status_code == 200
        assert resp.json()["active"] is True

        status = client.get("/api/status").json()
        assert status["autonomousActive"] is True

        # 2. Toggle OFF
        resp = client.post("/api/autonomous/toggle")
        assert resp.status_code == 200
        assert resp.json()["active"] is False

        status = client.get("/api/status").json()
        assert status["autonomousActive"] is False

        # 3. Start explicit
        resp = client.post("/api/autonomous/start")
        assert resp.status_code == 200
        assert resp.json()["active"] is True

        status = client.get("/api/status").json()
        assert status["autonomousActive"] is True
        assert status["obstacleSafetyEnabled"] is True

        # 4. Modifying safety while autonomous is active is rejected with 409
        safety_resp = client.post(
            "/api/safety/obstacles",
            json={"enabled": False, "adult_authorised": True},
        )
        assert safety_resp.status_code == 409

        # 5. Global stop endpoint stops autonomous
        resp = client.post("/api/execution/stop")
        assert resp.status_code == 200

        status = client.get("/api/status").json()
        assert status["autonomousActive"] is False
