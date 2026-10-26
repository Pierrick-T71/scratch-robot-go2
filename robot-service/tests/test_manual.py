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
