"""Tests du mode veille du robot."""

import pytest
from fastapi.testclient import TestClient

from go2_service.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


class TestStandbyAPI:
    def test_standby_initial_status(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["standby"] is False
        assert data["standbyTransition"] is None

    def test_toggle_standby_cycle(self, client):
        # 1. Activation de la veille
        resp = client.post("/api/robot/standby", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["standby"] is True

        # Vérification du statut
        statut = client.get("/api/status").json()
        assert statut["standby"] is True
        assert statut["posture"] == "lie_down"

        # 2. Commandes bloquées pendant la veille
        # - Lancement d'un programme
        prog_resp = client.post(
            "/api/execution/start",
            json={
                "program": {
                    "statements": [{"kind": "wait", "seconds": 1.0, "line": 1}]
                }
            },
        )
        assert prog_resp.status_code == 409
        assert "en veille" in prog_resp.json()["detail"].lower()

        # - Mode manuel
        man_resp = client.post("/api/manual/start", json={"adult_authorised": True})
        assert man_resp.status_code == 409
        assert "en veille" in man_resp.json()["detail"].lower()

        move_resp = client.post(
            "/api/manual/move", json={"direction": "forward", "seq": 1}
        )
        assert move_resp.status_code == 409

        jump_resp = client.post("/api/manual/jump")
        assert jump_resp.status_code == 409

        # - Changement de mode ou sécurité
        mode_resp = client.post(
            "/api/mode", json={"mode": "real", "adult_authorised": True}
        )
        assert mode_resp.status_code == 409

        safe_resp = client.post(
            "/api/safety/obstacles", json={"enabled": False, "adult_authorised": True}
        )
        assert safe_resp.status_code == 409

        # 3. Réveil du robot
        wake_resp = client.post("/api/robot/standby", json={"enabled": False})
        assert wake_resp.status_code == 200
        assert wake_resp.json()["standby"] is False

        # Vérification après réveil
        statut_reveil = client.get("/api/status").json()
        assert statut_reveil["standby"] is False
        assert statut_reveil["posture"] == "stand"

        # Le mode manuel et les commandes redeviennent accessibles
        man_ok = client.post("/api/manual/start", json={"adult_authorised": True})
        assert man_ok.status_code == 200
        assert man_ok.json()["active"] is True
        client.post("/api/manual/stop")

    def test_standby_stops_manual_active(self, client):
        client.post("/api/manual/start", json={"adult_authorised": True})
        assert client.get("/api/status").json()["manualActive"] is True

        resp = client.post("/api/robot/standby", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["standby"] is True

        statut = client.get("/api/status").json()
        assert statut["standby"] is True
        assert statut["manualActive"] is False


