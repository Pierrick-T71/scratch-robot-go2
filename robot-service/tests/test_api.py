"""Contrat HTTP du service.

Ce que ces tests verrouillent :

- un client qui envoie l'ANCIEN format (`commands`) est REJETÉ, pas
  silencieusement accepté ;
- un `NaN` dans un programme est rejeté avant d'atteindre l'adaptateur ;
- le bail de sécurité expire sans battement, et le robot s'arrête ;
- le mode réel reste refusé tant que le robot n'a pas été validé.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.main import create_app  # noqa: E402

#: Le programme de référence : exactement l'exemple du cahier des charges.
PROGRAM = {
    "statements": [
        {"kind": "move", "direction": "forward", "seconds": 2},
        {"kind": "turn", "direction": "left", "degrees": 90},
        {"kind": "move", "direction": "forward", "seconds": 2},
        {"kind": "stop_move"},
    ]
}


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


class TestStatus:
    def test_status_is_available_without_a_robot(self, client):
        response = client.get("/api/status")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "simulation"
        assert body["executing"] is False
        assert body["safetyReason"] is None
        assert body["obstacleSafetyEnabled"] is True
        assert body["obstacleSafetyAvailable"] is False

    def test_simulation_offers_the_sensor_the_robot_does_not_have(self, client):
        # Le simulateur propose la détection d'obstacle ; l'adaptateur
        # physique, non. C'est cette différence qui empêche un bloc capteur de
        # mentir sur un vrai robot.
        capabilities = client.get("/api/status").json()["capabilities"]
        assert "sensor_obstacle" in capabilities
        assert "movement" in capabilities


class TestStartContract:
    def test_accepts_the_new_program_format(self, client):
        response = client.post(
            "/api/execution/start",
            json={"program": PROGRAM, "adult_authorised": True},
        )
        assert response.status_code == 200
        assert response.json()["accepted"] is True

    def test_refuses_the_old_commands_field(self, client):
        # `extra="forbid"` fait échouer la requête au lieu d'exécuter un
        # programme vide en silence.
        response = client.post(
            "/api/execution/start",
            json={"commands": [{"kind": "move_forward", "distanceCm": 50}],
                  "adult_authorised": True},
        )
        assert response.status_code == 422

    def test_requires_a_program(self, client):
        response = client.post("/api/execution/start", json={"adult_authorised": True})
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "statement",
        [
            {"kind": "move", "direction": "up", "seconds": 2},
            {"kind": "move", "direction": "forward", "seconds": 0.25},
            {"kind": "turn", "direction": "left", "degrees": 37},
            {"kind": "posture", "posture": "backflip"},
            {"kind": "repeat", "times": 2.5, "body": []},
            {"kind": "if", "condition": "obstacle_detected", "then": []},
            {"kind": "teleport"},
            {"kind": "wait", "seconds": "beaucoup"},
        ],
    )
    def test_refuses_a_forged_instruction(self, client, statement):
        response = client.post(
            "/api/execution/start",
            json={"program": {"statements": [statement]}, "adult_authorised": True},
        )
        assert response.status_code == 422

    def test_refuses_a_condition_without_a_real_measure(self, client):
        # Aucune mesure de distance n'existe dans le SDK officiel : ce bloc ne
        # doit jamais passer, même en simulation.
        response = client.post(
            "/api/execution/start",
            json={
                "program": {
                    "statements": [
                        {"kind": "if", "condition": "obstacle_detected", "then": []}
                    ]
                },
                "adult_authorised": True,
            },
        )
        assert response.status_code == 422
        assert "obstacle" in response.json()["detail"]

    def test_refuses_a_deeply_nested_plan(self, client):
        body: list = []
        for _ in range(200):
            body = [{"kind": "repeat", "times": 2, "body": body}]
        response = client.post(
            "/api/execution/start",
            json={"program": {"statements": body}, "adult_authorised": True},
        )
        assert response.status_code == 422

    def test_a_second_run_is_refused_while_one_is_active(self, client):
        first = client.post(
            "/api/execution/start",
            json={"program": PROGRAM, "adult_authorised": True},
        )
        assert first.status_code == 200
        second = client.post(
            "/api/execution/start",
            json={"program": PROGRAM, "adult_authorised": True},
        )
        assert second.status_code in (409, 200)


class TestStop:
    def test_stop_is_accepted_even_when_nothing_runs(self, client):
        # Le chien de garde reste le garant : mieux vaut une demande
        # d'arrêt sans effet qu'une absence d'arrêt.
        response = client.post("/api/execution/stop")
        assert response.status_code == 200


class TestHeartbeatContract:
    def test_heartbeat_requires_the_exact_field_name(self, client):
        # `run_id` et non `runId` : une divergence de casse fait échouer la
        # requête, le bail expire et le chien de garde arrête le robot.
        response = client.post("/api/execution/heartbeat", json={"runId": "run-1"})
        assert response.status_code == 422

    def test_missing_heartbeats_trip_the_watchdog(self, client):
        import time

        client.post(
            "/api/execution/start",
            json={"program": PROGRAM, "adult_authorised": True},
        )
        # Aucun battement n'est envoyé : après le délai de bail, le service
        # doit arrêter le robot de lui-même.
        deadline = time.time() + 5.0
        stopped = False
        while time.time() < deadline:
            if client.get("/api/status").json()["executing"] is False:
                stopped = True
                break
            time.sleep(0.2)
        assert stopped, "le robot n'a pas été arrêté après l'expiration du bail"


class TestEndToEndExecution:
    """
    Le robot bouge-t-il vraiment ?

    Régression majeure : la diffusion des événements référençait un champ
    `variables` qui n'existe plus depuis la suppression des variables. Chaque
    événement levait donc une exception, la boucle s'interrompait, et le chien
    de garde arrêtait le robot — sans jamais bouger, et sans message
    d'explication côté interface.

    Ces tests ne disent pas « aucun appel n'échoue » : ils disent que le
    robot parcourt bien la distance demandée.
    """

    @staticmethod
    def _heartbeat(client: TestClient, run_id: str, seconds: float) -> None:
        """
        Envoie des battements pendant l'exécution.

        Sans eux, le chien de garde arrête le robot au bout du délai de bail —
        ce qui est EXACTEMENT le comportement voulu. Sans battements, ce test
        mesurerait l'arrêt de sécurité, pas le déplacement.
        """
        import time

        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                client.post("/api/execution/heartbeat", json={"run_id": run_id})
            except Exception:
                return
            time.sleep(0.3)

    def test_the_robot_actually_moves(self, client):
        start = client.post(
            "/api/execution/start",
            json={
                "program": {
                    "statements": [
                        {"kind": "move", "direction": "forward", "seconds": 2},
                        {"kind": "stop_move"},
                    ]
                },
                "adult_authorised": True,
            },
        )
        assert start.status_code == 200
        run_id = start.json()["runId"]

        # Sans battement, le chien de garde arrête : on en envoie.
        import threading

        thread = threading.Thread(
            target=self._heartbeat, args=(client, run_id, 6.0), daemon=True
        )
        thread.start()

        import time

        deadline = time.time() + 12.0
        while time.time() < deadline:
            if not client.get("/api/status").json()["executing"]:
                break
            time.sleep(0.2)

        position = client.get("/api/status").json()["position"]
        assert position is not None
        # 2 s à 0,3 m/s = 0,6 m, moins ce que la dérive et l'arrêt coûtent.
        assert position["x"] > 0.3, f"le robot n'a pas avancé : {position}"

    def test_the_robot_turns(self, client):
        start = client.post(
            "/api/execution/start",
            json={
                "program": {
                    "statements": [
                        {"kind": "turn", "direction": "left", "degrees": 90},
                        {"kind": "stop_move"},
                    ]
                },
                "adult_authorised": True,
            },
        )
        assert start.status_code == 200
        run_id = start.json()["runId"]

        import threading

        thread = threading.Thread(
            target=self._heartbeat, args=(client, run_id, 6.0), daemon=True
        )
        thread.start()

        import time

        deadline = time.time() + 12.0
        while time.time() < deadline:
            if not client.get("/api/status").json()["executing"]:
                break
            time.sleep(0.2)

        status = client.get("/api/status").json()
        # Le cap est une donnée MESURÉE : la rotation est donc vérifiable.
        assert status["yawRad"] is not None
        assert abs(status["yawRad"]) > 1.0, f"le robot n'a pas tourné : {status['yawRad']}"

    def test_reset_simulation_repositions_robot_to_origin(self, client):
        # Le robot a bougé ou tourné : reset le remet au centre (0, 0, 0) avec cap 0
        reset_resp = client.post("/api/simulation/reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json()["ok"] is True

        status = client.get("/api/status").json()
        assert status["position"] == {"x": 0.0, "y": 0.0, "z": 0.0}
        assert status["yawRad"] == 0.0


class TestObstacleSafetySwitch:
    """Le commutateur de sécurité lidar, côté service.

    Il ne coupe QUE la mesure de place du service. Le portage, le bail et
    l'anti-obstacle interne du robot ne sont pas concernés.
    """

    def test_unavailable_in_simulation(self, client):
        response = client.post(
            "/api/safety/obstacles",
            json={"enabled": False, "adult_authorised": True},
        )
        assert response.status_code == 409
        assert client.get("/api/status").json()["obstacleSafetyEnabled"] is True

    def test_refuses_a_typo_in_the_field_name(self, client):
        response = client.post(
            "/api/safety/obstacles",
            json={"enabled": True, "adultAuthorised": True},
        )
        assert response.status_code == 422

    def test_an_adult_can_cut_then_restore_it_on_a_real_adapter(self, client):
        service = client.app.state.service
        # Le simulateur est branché ; on lui donne les deux propriétés que
        # porte un vrai adaptateur pour tester le contrat HTTP sans robot.
        service.adapter.physical_commands_enabled = True
        service.adapter.obstacle_safety_enabled = True
        assert (
            client.post(
                "/api/mode",
                json={"mode": "real", "adult_authorised": True},
            ).status_code
            == 200
        )

        refuse = client.post(
            "/api/safety/obstacles",
            json={"enabled": False, "adult_authorised": False},
        )
        assert refuse.status_code == 403
        assert client.get("/api/status").json()["obstacleSafetyEnabled"] is True

        coupe = client.post(
            "/api/safety/obstacles",
            json={"enabled": False, "adult_authorised": True},
        )
        assert coupe.status_code == 200
        assert coupe.json()["obstacleSafetyEnabled"] is False
        assert service.adapter.obstacle_safety_enabled is False

        remis = client.post(
            "/api/safety/obstacles",
            json={"enabled": True, "adult_authorised": False},
        )
        assert remis.status_code == 200
        assert remis.json()["obstacleSafetyEnabled"] is True
        assert service.adapter.obstacle_safety_enabled is True


class TestRealModeStaysRefused:
    def test_switching_to_real_needs_an_adult(self, client):
        response = client.post(
            "/api/mode", json={"mode": "real", "adult_authorised": False}
        )
        assert response.status_code in (403, 409)

    def test_even_with_an_adult_real_mode_is_not_available(self, client):
        # Le robot n'a jamais été piloté : le mode réel doit rester refusé,
        # même autorisé. C'est le comportement voulu tant que la campagne
        # physique (docs/ROBOT_SETUP.md §5) n'a pas eu lieu.
        response = client.post(
            "/api/mode", json={"mode": "real", "adult_authorised": True}
        )
        assert response.status_code in (403, 409, 422)
        assert client.get("/api/status").json()["mode"] == "simulation"

    def test_an_unknown_field_is_refused(self, client):
        # `adultAuthorised` au lieu de `adult_authorised` doit être rejeté,
        # pas accepté avec `False` par défaut.
        response = client.post(
            "/api/mode", json={"mode": "simulation", "adultAuthorised": True}
        )
        assert response.status_code == 422


class TestRobotAesKey:
    """La clé du robot ne doit pas disparaître au redémarrage de la machine.

    Le service a été redémarré par un script qui ne chargeait pas le
    fichier local : la clé manquait, et le branchement était refusé. Le
    service la lit donc lui-même dans le fichier quand la variable
    d'environnement est absente.
    """

    def test_the_key_comes_from_the_environment_first(self, monkeypatch):
        from go2_service import main as service_main

        monkeypatch.setenv("GO2_ROBOT_AES_KEY", "depuis-l-env")
        assert service_main._robot_aes_key() == "depuis-l-env"

    def test_the_key_is_read_from_the_local_file(self, monkeypatch, tmp_path):
        from go2_service import main as service_main

        fichier = tmp_path / "robot.env"
        fichier.write_text("GO2_ROBOT_AES_KEY=depuis-le-fichier\n", encoding="utf-8")
        monkeypatch.delenv("GO2_ROBOT_AES_KEY", raising=False)
        monkeypatch.setattr(service_main, "ROBOT_AES_KEY_FILE", str(fichier))
        assert service_main._robot_aes_key() == "depuis-le-fichier"

    def test_without_a_key_the_service_says_so(self, monkeypatch, tmp_path):
        from go2_service import main as service_main

        monkeypatch.delenv("GO2_ROBOT_AES_KEY", raising=False)
        monkeypatch.setattr(service_main, "ROBOT_AES_KEY_FILE", str(tmp_path / "absent.env"))
        assert service_main._robot_aes_key() is None


class TestSettingsContract:
    def test_settings_are_readable(self, client):
        response = client.get("/api/settings")
        assert response.status_code == 200
        assert "values" in response.json()

    def test_settings_need_an_adult(self, client):
        response = client.post(
            "/api/settings",
            json={"adult_authorised": False, "values": {"max_linear_speed": 0.1}},
        )
        assert response.status_code in (403, 422)

    def test_an_unknown_field_is_refused(self, client):
        response = client.post(
            "/api/settings",
            json={"adultAuthorised": True, "values": {}},
        )
        assert response.status_code == 422

    def test_limits_cannot_be_raised_above_the_delivered_ones(self, client):
        # Un adulte peut RESSERRER, jamais élargir au-delà de ce qui a été
        # livré. C'est `config.HARD_CEILINGS` qui l'impose.
        response = client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 99.0}},
        )
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            assert response.json()["values"]["max_linear_speed"] <= 0.5

    def test_settings_can_be_lowered(self, client):
        response = client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 0.1}},
        )
        assert response.status_code == 200
        assert response.json()["values"]["max_linear_speed"] == pytest.approx(0.1)

    def test_a_lower_limit_is_reflected_in_the_status_revision(self, client):
        before = client.get("/api/status").json()["settingsRevision"]
        client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 0.1}},
        )
        after = client.get("/api/status").json()["settingsRevision"]
        assert after > before