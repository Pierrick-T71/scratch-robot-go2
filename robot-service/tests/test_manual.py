"""Tests du pilotage manuel (mode manuel, barre espace / saut, directions combinées)."""

import pytest
from fastapi.testclient import TestClient

from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.config import load_limits
from go2_service.main import create_app
from go2_service.manual import DIRECTIONS, ManualControl, ManualNotActive


@pytest.fixture
def adapter():
    return SimulatedAdapter(load_limits())


@pytest.fixture
def manual(adapter):
    return ManualControl(adapter)


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


class TestManualControl:
    @pytest.mark.asyncio
    async def test_jump_requires_active_session(self, manual):
        with pytest.raises(ManualNotActive):
            await manual.jump()

    @pytest.mark.asyncio
    async def test_jump_when_active(self, manual):
        manual.start()
        blocked, msg = await manual.jump()
        assert not blocked
        assert msg is None

    @pytest.mark.asyncio
    async def test_compound_directions_accepted(self, manual):
        manual.start()
        for direction in (
            "forward+turn_left",
            "forward+turn_right",
            "backward+turn_left",
            "backward+turn_right",
        ):
            assert direction in DIRECTIONS
            blocked, msg = await manual.set_direction(direction)
            assert not blocked
            assert msg is None
            assert manual.direction == direction

    @pytest.mark.asyncio
    async def test_invalid_direction_rejected(self, manual):
        manual.start()
        with pytest.raises(ValueError):
            await manual.set_direction("diagonal_up")



    @pytest.mark.asyncio
    async def test_arbitration_between_sources(self, manual):
        manual.start()
        # Keyboard takes control
        blocked, msg = await manual.set_direction("forward", seq=1, source="keyboard")
        assert not blocked
        assert manual.active_source == "keyboard"

        # Mobile attempts to steer while keyboard is active
        blocked, msg = await manual.set_direction("turn_left", seq=1, source="mobile")
        assert blocked
        assert "déjà piloté par keyboard" in msg
        assert manual.direction == "forward"
        assert manual.active_source == "keyboard"

        # Keyboard releases
        blocked, msg = await manual.set_direction(None, seq=2, source="keyboard")
        assert not blocked
        assert manual.direction is None
        assert manual.active_source is None

        # Now mobile takes control
        blocked, msg = await manual.set_direction("turn_right", seq=2, source="mobile")
        assert not blocked
        assert manual.direction == "turn_right"
        assert manual.active_source == "mobile"

    @pytest.mark.asyncio
    async def test_crouch_mode_toggle_and_speeds(self, manual):
        manual.start()
        assert not manual.crouch_mode
        assert manual.speed_mps == 0.6
        assert manual.turn_speed_rps == 1.0

        blocked, msg = await manual.set_crouch_mode(True)
        assert not blocked
        assert msg is None
        assert manual.crouch_mode
        assert manual.speed_mps == 0.20
        assert manual.turn_speed_rps == 0.50

        blocked, msg = await manual.set_direction("forward")
        assert not blocked
        assert manual.direction == "forward"

        blocked, msg = await manual.set_crouch_mode(False)
        assert not blocked
        assert not manual.crouch_mode
        assert manual.speed_mps == 0.6
        assert manual.turn_speed_rps == 1.0

    @pytest.mark.asyncio
    async def test_sprint_forward_speeds(self, manual):
        manual.start()
        assert not manual.sprint
        assert manual.speed_mps == 0.6

        # Sprint forward activates 2.5 m/s
        blocked, msg = await manual.set_direction("forward", seq=1, sprint=True)
        assert not blocked
        assert manual.sprint is True
        assert manual.speed_mps == 2.5

        # Releasing sprint while keeping forward reverts to 0.6 m/s
        blocked, msg = await manual.set_direction("forward", seq=2, sprint=False)
        assert not blocked
        assert manual.sprint is False
        assert manual.speed_mps == 0.6

        # Sprint with backward is ignored (only forward sprints)
        blocked, msg = await manual.set_direction("backward", seq=3, sprint=True)
        assert not blocked
        assert manual.sprint is False
        assert manual.speed_mps == 0.6

        # Sprint with forward+turn_left activates 2.5 m/s
        blocked, msg = await manual.set_direction("forward+turn_left", seq=4, sprint=True)
        assert not blocked
        assert manual.sprint is True
        assert manual.speed_mps == 2.5

        # Release motion resets sprint
        blocked, msg = await manual.set_direction(None, seq=5)
        assert not blocked
        assert manual.sprint is False
        assert manual.direction is None


class TestManualEndpoints:
    def test_jump_endpoint_requires_manual_active(self, client):
        resp = client.post("/api/manual/jump")
        assert resp.status_code == 409
        assert "Le mode manuel n’est pas ouvert" in resp.json()["detail"]

    def test_start_jump_move_and_stop(self, client):
        start_resp = client.post("/api/manual/start", json={"adult_authorised": True})
        assert start_resp.status_code == 200
        assert start_resp.json()["active"] is True

        # Test compound move
        move_resp = client.post(
            "/api/manual/move",
            json={"direction": "forward+turn_left", "seq": 1},
        )
        assert move_resp.status_code == 200
        assert move_resp.json()["active"] is True
        assert move_resp.json()["blocked"] is False

        # Test jump
        jump_resp = client.post("/api/manual/jump")
        assert jump_resp.status_code == 200
        assert jump_resp.json()["ok"] is True
        assert jump_resp.json()["blocked"] is False

# Test stop
        stop_resp = client.post("/api/manual/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["active"] is False

    def test_arbitration_and_status_payload(self, client):
        client.post("/api/manual/start", json={"adult_authorised": True})

        # Keyboard moves
        move_resp = client.post(
            "/api/manual/move",
            json={"direction": "forward", "seq": 1, "source": "keyboard"},
        )
        assert move_resp.json()["blocked"] is False

        # Status shows manualSource keyboard and valid lanIp
        status_resp = client.get("/api/status")
        assert status_resp.json()["manualActive"] is True
        assert status_resp.json()["manualSource"] == "keyboard"
        assert status_resp.json()["lanIp"] != ""

        # Mobile command is blocked by arbitration
        mobile_resp = client.post(
            "/api/manual/move",
            json={"direction": "backward", "seq": 1, "source": "mobile"},
        )
        assert mobile_resp.json()["blocked"] is True
        assert "déjà piloté" in mobile_resp.json()["message"]

        # Keyboard releases
        client.post(
            "/api/manual/move",
            json={"direction": None, "seq": 2, "source": "keyboard"},
        )

        # Mobile jump succeeds
        jump_resp = client.post(
            "/api/manual/jump",
            json={"source": "mobile"},
        )
        assert jump_resp.status_code == 200
        assert jump_resp.json()["ok"] is True

    def test_crouch_endpoint(self, client):
        client.post("/api/manual/start", json={"adult_authorised": True})

        # Enable crouch
        resp = client.post("/api/manual/crouch", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["crouchActive"] is True

        # Check status reflects crouchActive
        status = client.get("/api/status").json()
        assert status["manualCrouchActive"] is True

        # Disable crouch
        resp = client.post("/api/manual/crouch", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["crouchActive"] is False

        status = client.get("/api/status").json()
        assert status["manualCrouchActive"] is False

    def test_sprint_endpoint(self, client):
        client.post("/api/manual/start", json={"adult_authorised": True})

        # Sprint forward
        resp = client.post(
            "/api/manual/move",
            json={"direction": "forward", "sprint": True, "seq": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["sprint"] is True

        # Stop sprint while continuing forward
        resp = client.post(
            "/api/manual/move",
            json={"direction": "forward", "sprint": False, "seq": 2},
        )
        assert resp.status_code == 200
        assert resp.json()["sprint"] is False

        # Release
        resp = client.post(
            "/api/manual/move",
            json={"direction": None, "seq": 3},
        )
        assert resp.status_code == 200
        assert resp.json()["sprint"] is False
