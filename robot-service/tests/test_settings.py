"""Tests des réglages d'adulte exposed par `/api/settings`.

Ces tests verrouillent la propriété de sécurité centrale : **un réglage ne peut
jamais dépasser le plafond écrit dans le code**, même si le client est modifié.
C'est ce qui distingue une interface de configuration d'un levier de sécurité.
"""

from __future__ import annotations

import pytest

from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.config import (
    ADJUSTABLE,
    HARD_CEILINGS,
    HARD_FLOORS,
    ConfigurationError,
    adjustable_settings,
    apply_settings,
    load_limits,
    SettingsError,
)
from go2_service.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def limits():
    return load_limits()


@pytest.fixture
def fresh_limits(limits):
    """Copie indépendante : les tests modifient les limites en place."""
    import copy

    return copy.deepcopy(limits)


class TestLimitsIsolation:
    """`load_limits()` est mis en cache : les applications doivent être isolées.

    Sans copie, `apply_settings()` modifierait en place l'objet partagé, et
    le succès d'un test dépendrait de l'ordre d'exécution. Symptôme observé :
    un test d'arrêt de sécurité échouait par intermittence selon que les tests
    de réglages aient tourné avant lui.
    """

    def test_create_app_does_not_mutate_the_cached_limits(self, limits):
        before = limits.motion.max_linear_speed
        app = create_app(SimulatedAdapter(limits, tick_multiplier=50.0))
        # Le service doit avoir reçu sa PROPRE copie.
        assert app.state.service.limits is not limits
        assert app.state.service.limits.motion.max_linear_speed == before

    def test_settings_in_one_app_do_not_affect_another(self, limits):
        app_a = create_app(SimulatedAdapter(limits, tick_multiplier=50.0))
        app_b = create_app(SimulatedAdapter(limits, tick_multiplier=50.0))
        apply_settings(app_a.state.service.limits, {"max_linear_speed": 0.12})
        assert app_a.state.service.limits.motion.max_linear_speed == 0.12
        assert app_b.state.service.limits.motion.max_linear_speed == 0.30
        assert limits.motion.max_linear_speed == 0.30


class TestSharedFileUnchanged:
    def test_file_matches_hard_ceilings(self, limits):
        """Le fichier partagé doit rester au niveau des plafonds.

        S'ils divergeaient, les plafonds ne seraient plus la référence et un
        réglage pourrait dépasser la valeur livré dans le dépôt.
        """
        ceilings = vars(HARD_CEILINGS)
        assert limits.motion.max_linear_speed == ceilings["max_linear_speed"]
        assert limits.motion.max_angular_speed == ceilings["max_angular_speed"]
        assert (
            limits.motion.max_distance_per_step_cm
            == ceilings["max_distance_per_step_cm"]
        )
        assert limits.program.max_total_steps == ceilings["max_total_steps"]
        assert limits.program.max_program_seconds == ceilings["max_program_seconds"]

    def test_file_is_not_mutated_by_a_test_run(self, limits):
        """`load_limits` est mis en cache : le module de tests ne doit pas
        pouvoir modifier le réglage d'un autre test."""
        assert limits.motion.max_linear_speed == 0.30


class TestApplySettings:
    def test_applies_a_valid_value(self, fresh_limits):
        result = apply_settings(fresh_limits, {"max_linear_speed": 0.2})
        assert fresh_limits.motion.max_linear_speed == 0.2
        assert result["max_linear_speed"] == 0.2

    def test_omitted_fields_are_untouched(self, fresh_limits):
        before = fresh_limits.motion.max_angular_speed
        apply_settings(fresh_limits, {"max_linear_speed": 0.15})
        assert fresh_limits.motion.max_angular_speed == before

    def test_rejects_value_above_ceiling(self, fresh_limits):
        """Le point capital : impossible de dépasser le plafond du code."""
        with pytest.raises(SettingsError):
            apply_settings(fresh_limits, {"max_linear_speed": 0.5})
        assert fresh_limits.motion.max_linear_speed == 0.30, "aucune écriture partielle"

    def test_rejects_value_below_floor(self, fresh_limits):
        with pytest.raises(SettingsError):
            apply_settings(fresh_limits, {"max_linear_speed": 0.01})

    def test_accepts_exact_ceiling(self, fresh_limits):
        apply_settings(fresh_limits, {"max_linear_speed": 0.30})
        assert fresh_limits.motion.max_linear_speed == 0.30

    def test_rejects_unknown_field(self, fresh_limits):
        with pytest.raises(SettingsError):
            apply_settings(fresh_limits, {"max_speed_of_light": 3})

    def test_rejects_booleans(self, fresh_limits):
        with pytest.raises(SettingsError):
            apply_settings(fresh_limits, {"max_linear_speed": True})

    def test_rejects_strings(self, fresh_limits):
        with pytest.raises(SettingsError):
            apply_settings(fresh_limits, {"max_linear_speed": "0.2"})

    def test_rejects_non_finite(self, fresh_limits):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(SettingsError):
                apply_settings(fresh_limits, {"max_linear_speed": bad})

    def test_rejects_empty_payload(self, fresh_limits):
        before = adjustable_settings(fresh_limits)
        apply_settings(fresh_limits, {})
        assert adjustable_settings(fresh_limits) == before

    def test_rejects_incoherent_distance_total(self, fresh_limits):
        """La distance totale ne peut pas devenir inférieure à un pas."""
        with pytest.raises(SettingsError):
            apply_settings(
                fresh_limits,
                {
                    "max_distance_per_step_cm": 200.0,
                    "max_total_distance_cm": 100.0,
                },
            )

    def test_rejects_total_distance_impossible_within_steps(self, fresh_limits):
        """Le cumul ne doit pas dépasser ce que le nombre de pas permet.

        5 pas de 200 cm ne peuvent pas produire 1500 cm : réglage incohérent.
        """
        with pytest.raises(SettingsError):
            apply_settings(
                fresh_limits,
                {
                    "max_total_steps": 5,
                    "max_distance_per_step_cm": 200.0,
                    "max_total_distance_cm": 1500.0,
                },
            )

    def test_accepts_coherent_steps_and_distance(self, fresh_limits):
        """50 pas de 200 cm et 1000 cm de cumul : cohérent (50 x 200 >= 1000).

        50 est le plancher de `max_total_steps` : en dessous, une classe
        d'âge scolaire ne pourrait plus faire son carré.
        """
        apply_settings(
            fresh_limits,
            {
                "max_total_steps": 50,
                "max_distance_per_step_cm": 200.0,
                "max_total_distance_cm": 1000.0,
            },
        )
        assert fresh_limits.program.max_total_steps == 50
        assert fresh_limits.program.max_total_distance_cm == 1000.0

    def test_rejects_single_wait_longer_than_program(self, fresh_limits):
        """Une seule attente ne peut pas dépasser toute la durée autorisée."""
        with pytest.raises(SettingsError):
            apply_settings(
                fresh_limits,
                {"max_wait_seconds": 10.0, "max_program_seconds": 5.0},
            )

    def test_accepts_wait_below_program_duration(self, fresh_limits):
        apply_settings(
            fresh_limits,
            {"max_wait_seconds": 3.0, "max_program_seconds": 120.0},
        )
        assert fresh_limits.timing.max_wait_seconds == 3.0

    def test_all_adjustable_fields_have_floor_and_ceiling(self):
        for name in ADJUSTABLE:
            assert name in HARD_FLOORS, f"{name} sans plancher"
            assert hasattr(HARD_CEILINGS, ADJUSTABLE[name]), f"{name} sans plafond"

    def test_floors_are_strictly_below_ceilings(self):
        for name in ADJUSTABLE:
            assert HARD_FLOORS[name] < getattr(HARD_CEILINGS, ADJUSTABLE[name])


class TestSettingsApi:
    @pytest.fixture
    def app_client(self, limits):
        # `create_app` copie désormais les limites (elles sont modifiables en
        # place), donc l'adaptateur peut partager l'objet fourni par la fixture.
        adapter = SimulatedAdapter(limits, tick_multiplier=50.0)
        app = create_app(adapter)
        with TestClient(app) as client:
            yield client

    def test_get_returns_values_and_bounds(self, app_client):
        response = app_client.get("/api/settings")
        assert response.status_code == 200
        body = response.json()
        assert "values" in body
        assert "bounds" in body
        # Chaque réglage exposé doit avoir ses deux bornes.
        for field in body["values"]:
            assert field in body["bounds"]
            assert "min" in body["bounds"][field]
            assert "max" in body["bounds"][field]

    def test_get_bounds_never_exceed_hard_ceilings(self, app_client):
        bounds = app_client.get("/api/settings").json()["bounds"]
        for field, limit in bounds.items():
            assert limit["max"] == getattr(HARD_CEILINGS, ADJUSTABLE[field]), field

    def test_post_refuses_without_adult_authorisation(self, app_client):
        response = app_client.post(
            "/api/settings", json={"adult_authorised": False, "values": {"max_linear_speed": 0.1}}
        )
        assert response.status_code == 403

    def test_post_applies_with_authorisation(self, app_client):
        response = app_client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 0.15}},
        )
        assert response.status_code == 200
        assert response.json()["values"]["max_linear_speed"] == 0.15

    def test_post_refuses_value_above_ceiling(self, app_client):
        """Non-régression : le plafond est bien appliqué côté API."""
        # On note la valeur avant : elle peut avoir été modifiée par un
        # test précédent de la même classe.
        before = app_client.get("/api/settings").json()["values"]["max_linear_speed"]

        response = app_client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 5.0}},
        )
        assert response.status_code == 422

        # La valeur est restée exactement ce qu'elle était.
        after = app_client.get("/api/settings").json()["values"]["max_linear_speed"]
        assert after == before

    def test_post_rejects_camel_case_authorisation(self, app_client):
        """Non-régression : `adultAuthorised` doit être REFUSÉ.

        Bug réel rencontré : le frontend envoyait `adultAuthorised` et le
        modèle attend `adult_authorised`. Sans `extra="forbid"`, Pydantic
        ignorait le champ, `adult_authorised` valait `False`, et le service
        répondait « Seul un adulte peut modifier les réglages » — message
        trompeur alors que l'adulte avait bel et bien cliqué sur Appliquer.
        """
        before = app_client.get("/api/settings").json()["values"]["max_linear_speed"]

        response = app_client.post(
            "/api/settings",
            json={"adultAuthorised": True, "values": {"max_linear_speed": 0.15}},
        )
        assert response.status_code == 422

        # Et le réglage n'a pas été appliqué.
        assert app_client.get("/api/settings").json()["values"]["max_linear_speed"] == before

    def test_post_rejects_extra_field_on_start(self, app_client):
        """Même protection sur le démarrage d'un programme."""
        response = app_client.post(
            "/api/execution/start",
            json={
                "commands": [{"kind": "stop"}],
                "adultAuthorised": True,
            },
        )
        assert response.status_code == 422

    def test_post_rejects_extra_field_on_mode(self, app_client):
        response = app_client.post(
            "/api/mode",
            json={"mode": "simulation", "adultAuthorised": True},
        )
        assert response.status_code == 422

    def test_snake_case_start_is_accepted(self, app_client):
        """Le contrat réellement utilisé doit fonctionner."""
        response = app_client.post(
            "/api/execution/start",
            json={
                "program": {"statements": [{"kind": "stop_move"}]},
                "adult_authorised": True,
            },
        )
        assert response.status_code == 200

    def test_snake_case_mode_is_accepted(self, app_client):
        response = app_client.post(
            "/api/mode",
            json={"mode": "simulation", "adult_authorised": True},
        )
        assert response.status_code == 200

    def test_post_refuses_unknown_field(self, app_client):
        response = app_client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"evil": 1}},
        )
        assert response.status_code == 422

    def test_settings_change_bumps_revision(self, app_client):
        before = app_client.get("/api/status").json()["settingsRevision"]
        app_client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 0.2}},
        )
        after = app_client.get("/api/status").json()["settingsRevision"]
        assert after == before + 1

    def test_refused_change_does_not_bump_revision(self, app_client):
        before = app_client.get("/api/status").json()["settingsRevision"]
        app_client.post(
            "/api/settings",
            json={"adult_authorised": True, "values": {"max_linear_speed": 99.0}},
        )
        assert app_client.get("/api/status").json()["settingsRevision"] == before

    def test_settings_refused_during_execution(self, app_client):
        """Un programme ne doit pas changer de regles sous ses pieds.

        TestClient etant synchrone, la tache de fond n'avance pas entre deux
        requetes : attendre executing == True expirerait toujours. On force
        l'etat, et on verifie la garde elle-meme.
        """
        from go2_service.execution import ActiveExecution

        engine = app_client.app.state.service.engine
        engine._active = ActiveExecution(run_id="en-cours")
        try:
            assert engine.is_running is True
            response = app_client.post(
                "/api/settings",
                json={"adult_authorised": True, "values": {"max_linear_speed": 0.2}},
            )
            assert response.status_code == 409
        finally:
            engine._active = None


class TestConfigurationErrorStillRaised:
    def test_missing_file_message_is_actionable(self):
        error = ConfigurationError("Fichier de configuration introuvable : /x/y.json")
        assert "introuvable" in str(error)
        # Doit indiquer le chemin pour être exploitable en séance.
        assert "/x/y.json" in str(error)