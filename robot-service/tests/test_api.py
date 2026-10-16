"""Tests d'intégration : l'API FastAPI avec l'adaptateur simulé.

Ces tests exercent la chaîne complète : requête HTTP -> validation
autoritative -> moteur -> adaptateur simulé -> événements.

Aucun test n'envoie de commande physique : l'adaptateur simulé est le seul
utilisé, et il refuse par construction tout accès au SDK.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.config import load_limits
from go2_service.main import create_app

SIM_SPEEDUP = 50.0


@pytest.fixture
def limits():
    return load_limits()


@pytest.fixture
def adapter(limits):
    """Simulateur rapide, pilotable depuis le test."""
    return SimulatedAdapter(limits, tick_multiplier=SIM_SPEEDUP)


@pytest.fixture
def client(adapter):
    app = create_app(adapter)
    with TestClient(app) as test_client:
        test_client.adapter = adapter  # accès direct pour les assertions
        yield test_client


class TestStatusEndpoint:
    def test_starts_in_simulation(self, client):
        """Le mode initial doit TOUJOURS être la simulation."""
        response = client.get("/api/status")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "simulation"
        assert body["connected"] is True
        assert body["executing"] is False

    def test_reports_capabilities(self, client):
        body = client.get("/api/status").json()
        assert set(body["capabilities"]) == {"movement", "posture", "wait", "stop"}


class TestModeSwitch:
    def test_real_mode_refused_without_adult_authorisation(self, client):
        response = client.post(
            "/api/mode", json={"mode": "real", "adult_authorised": False}
        )
        assert response.status_code == 403
        assert client.get("/api/status").json()["mode"] == "simulation"

    def test_real_mode_refused_even_with_authorisation(self, client):
        """L'adaptateur simulé n'est PAS validé pour le pilotage réel."""
        response = client.post(
            "/api/mode", json={"mode": "real", "adult_authorised": True}
        )
        assert response.status_code == 403
        assert "validé" in response.json()["detail"]

    def test_can_return_to_simulation(self, client):
        response = client.post("/api/mode", json={"mode": "simulation"})
        assert response.status_code == 200
        assert response.json()["mode"] == "simulation"


class TestStartValidation:
    """Un client modifié ne doit pas pouvoir contourner la validation."""

    def test_rejects_unknown_command(self, client):
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "self_destruct"}], "adult_authorised": True},
        )
        assert response.status_code == 422
        assert "n’existe pas" in response.json()["detail"]

    def test_rejects_missing_parameter(self, client):
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "move_forward"}]},
        )
        assert response.status_code == 422

    def test_rejects_out_of_range_distance(self, client):
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "move_forward", "distanceCm": 9999}]},
        )
        assert response.status_code == 422

    def test_rejects_out_of_range_repeat_explosion(self, client):
        """Un programme trop long est refusé avant tout mouvement."""
        commands = [{"kind": "wait", "seconds": 1}] * 600
        response = client.post(
            "/api/execution/start", json={"commands": commands}
        )
        assert response.status_code == 422

    def test_rejects_non_list_program(self, client):
        response = client.post(
            "/api/execution/start", json={"commands": {"kind": "stop"}}
        )
        assert response.status_code == 422

    def test_rejects_boolean_as_distance(self, client):
        """`true` ne doit pas passer pour 1 cm."""
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "move_forward", "distanceCm": True}]},
        )
        assert response.status_code == 422

    def test_rejects_nan_distance(self, client):
        response = client.post(
            "/api/execution/start",
            content='{"commands": [{"kind":"move_forward","distanceCm": NaN}]}',
            headers={"Content-Type": "application/json"},
        )
        # NaN n'est pas du JSON valide : la requête est refusée en amont.
        assert response.status_code == 422

    def test_rejects_empty_program(self, client):
        response = client.post("/api/execution/start", json={"commands": []})
        assert response.status_code == 422


class TestExecutionFlow:
    def _wait_idle(self, client, timeout=10.0):
        """Attend la fin de l'exécution via l'endpoint d'état."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not client.get("/api/status").json()["executing"]:
                return True
            time.sleep(0.02)
        return False

    def test_runs_a_valid_program(self, client):
        response = client.post(
            "/api/execution/start",
            json={
                "commands": [
                    {"kind": "stand_up"},
                    {"kind": "move_forward", "distanceCm": 50},
                    {"kind": "turn_left", "angleDeg": 90},
                    {"kind": "wait", "seconds": 0.2},
                ],
                "adult_authorised": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["accepted"] is True
        assert self._wait_idle(client)

    def test_returns_run_id(self, client):
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "stop"}]},
        )
        assert "runId" in response.json()

    def test_start_responds_without_waiting_for_completion(self, client):
        """Le client ne doit pas rester bloqué pendant toute l'exécution."""
        import time

        commands = [{"kind": "move_forward", "distanceCm": 200}] * 3
        start = time.monotonic()
        response = client.post(
            "/api/execution/start", json={"commands": commands}
        )
        elapsed = time.monotonic() - start
        assert response.status_code == 200
        assert elapsed < 2.0, "le démarrage doit être asynchrone"
        self._wait_idle(client)

    def test_rejects_concurrent_start(self, client):
        import time

        commands = [{"kind": "move_forward", "distanceCm": 200}] * 4
        first = client.post("/api/execution/start", json={"commands": commands})
        assert first.status_code == 200
        # Une seconde tentative pendant l'exécution doit être refusée.
        second = client.post("/api/execution/start", json={"commands": commands})
        assert second.status_code == 409
        self._wait_idle(client)

    def test_stop_endpoint_always_answers(self, client):
        response = client.post("/api/execution/stop")
        assert response.status_code == 200
        assert response.json()["stopping"] is True

    def test_stop_interrupts_running_program(self, client):
        import time

        commands = [{"kind": "move_forward", "distanceCm": 200}] * 5
        client.post("/api/execution/start", json={"commands": commands})
        time.sleep(0.05)
        assert client.post("/api/execution/stop").status_code == 200
        assert self._wait_idle(client)

    def test_heartbeat_endpoint(self, client):
        commands = [{"kind": "move_forward", "distanceCm": 200}] * 3
        run = client.post("/api/execution/start", json={"commands": commands}).json()
        response = client.post(
            "/api/execution/heartbeat", json={"run_id": run["runId"]}
        )
        assert response.status_code == 200
        self._wait_idle(client)


class TestSimulatorFaultInjection:
    def test_connection_loss_during_motion_is_reported(self, client):
        client.adapter.simulate_disconnect_during_motion = True
        commands = [{"kind": "move_forward", "distanceCm": 200}]
        response = client.post("/api/execution/start", json={"commands": commands})
        assert response.status_code == 200

        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not client.get("/api/status").json()["executing"]:
                break
            time.sleep(0.02)

        status = client.get("/api/status").json()
        assert status["connected"] is False

    def test_command_failure_does_not_crash_service(self, client):
        client.adapter.fail_next_command = True
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "move_forward", "distanceCm": 50}]},
        )
        assert response.status_code == 200

        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not client.get("/api/status").json()["executing"]:
                break
            time.sleep(0.02)

        # Le service doit rester interrogeable après l'échec.
        assert client.get("/api/status").status_code == 200

    def test_service_survives_stuck_robot(self, client):
        client.adapter.simulate_stuck = True
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "move_forward", "distanceCm": 200}]},
        )
        assert response.status_code == 200

        import time

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if not client.get("/api/status").json()["executing"]:
                break
            time.sleep(0.02)

        assert client.get("/api/status").json()["executing"] is False


class TestHeartbeatContract:
    """Verrouille la forme EXACTE du payload envoyé par le frontend.

    Régression encountered en développement : le frontend envoyait
    `{ "runId": ... }` alors que le modèle attend `run_id`. Chaque
    battement était refusé en 422, le bail expirait, et le chien de garde
    arrêtait le robot au bout de 1,5 s. Ce test verrouille la forme correcte
    ET vérifie qu'un écart de casse est bien détecté.
    """

    def test_accepts_run_id_payload(self, client):
        response = client.post(
            "/api/execution/heartbeat", json={"run_id": "run-1-123"}
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_rejects_camel_case_payload(self, client):
        """`runId` doit être refusé : c'est précisément le bug rencontré."""
        response = client.post(
            "/api/execution/heartbeat", json={"runId": "run-1-123"}
        )
        assert response.status_code == 422

    def test_rejects_empty_payload(self, client):
        assert client.post("/api/execution/heartbeat", json={}).status_code == 422

    def test_rejects_oversized_run_id(self, client):
        response = client.post(
            "/api/execution/heartbeat", json={"run_id": "x" * 500}
        )
        assert response.status_code == 422

    def test_heartbeats_prevent_lease_expiry(self, client, limits):
        """Un client qui maintient le bail ne doit jamais être coupé.

        On observe le compteur du chien de garde plutôt que l'état
        d'exécution : le simulateur étant accéléré, le programme peut être
        déjà terminé à la fin de la fenêtre du bail.
        """
        import time

        service = client.app.state.service
        trips_before = service.watchdog.trips

        commands = [{"kind": "move_forward", "distanceCm": 200}] * 2
        client.post("/api/execution/start", json={"commands": commands})

        # Battements pendant toute la fenêtre du bail.
        deadline = time.monotonic() + limits.safety.lease_timeout_ms / 1000.0
        while time.monotonic() < deadline:
            response = client.post(
                "/api/execution/heartbeat", json={"run_id": "run-1"}
            )
            assert response.status_code == 200
            time.sleep(0.05)

        # Aucun arrêt de sécurité n'a dû être déclenché.
        assert service.watchdog.trips == trips_before

    def test_missing_heartbeats_do_trip_the_watchdog(self, limits):
        """Contrôle inverse : sans battement, la sécurité doit agir.

        Utilise un simulateur en temps RÉEL : avec l'adaptateur accéléré des
        autres tests, un programme se termine avant que le bail puisse
        expirer, et le test ne prouve plus rien.
        """
        import time

        adapter = SimulatedAdapter(limits, tick_multiplier=1.0)
        app = create_app(adapter)
        with TestClient(app) as slow:
            service = app.state.service
            trips_before = service.watchdog.trips

            # 10 s d'attente : la plus longue autorisée, soit largement plus
            # que la fenêtre de bail de 1,5 s.
            slow.post(
                "/api/execution/start",
                json={"commands": [{"kind": "wait", "seconds": 10}]},
            )

            time.sleep(limits.safety.lease_timeout_ms / 1000.0 + 0.5)

            assert service.watchdog.trips > trips_before
            slow.post("/api/execution/stop")


class TestNetworkExposure:
    def test_rejects_unknown_origin_on_websocket(self, client):
        """Une origine non autorisée doit être refusée."""
        with pytest.raises(Exception):
            with client.websocket_connect(
                "/ws/events", headers={"origin": "http://evil.example.com"}
            ):
                pass

    def test_accepts_allowed_origin_on_websocket(self, client):
        with client.websocket_connect(
            "/ws/events", headers={"origin": "http://localhost:5173"}
        ) as websocket:
            message = websocket.receive_json()
            assert message["type"] == "status"
            assert message["status"]["mode"] == "simulation"


class TestShutdownSafety:
    def test_shutdown_always_requests_stop(self, limits):
        """Quitter le service ne doit jamais laisser de mouvement en cours."""
        adapter = SimulatedAdapter(limits, tick_multiplier=SIM_SPEEDUP)
        calls = {"n": 0}
        original = adapter.request_stop

        async def counting():
            calls["n"] += 1
            await original()

        adapter.request_stop = counting

        app = create_app(adapter)
        with TestClient(app) as test_client:
            test_client.post(
                "/api/execution/start",
                json={"commands": [{"kind": "move_forward", "distanceCm": 200}] * 2},
            )

        assert calls["n"] >= 1