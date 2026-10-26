"""Arrêt de sécurité dans l'adaptateur WebRTC.

Les tests simulent les deux topics réels :

* `rt/lf/sportmodestate` : code d'état, position, roulis/tangage ;
* `rt/lf/lowstate` : efforts dans les pieds.

Ils vérifient qu'un portage envoie bien un arrêt au robot, relâche les
pattes avec `Damp`, verrouille les commandes suivantes, et laisse l'arrêt
lui-même toujours disponible.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.base import (  # noqa: E402
    Posture,
    RobotState,
    SafetyInterrupt,
    StopSignal,
)
from go2_service.adapters.motion import plan_command  # noqa: E402
from go2_service.adapters.webrtc import WebRTCAdapter  # noqa: E402
from go2_service.config import load_limits  # noqa: E402
from go2_service.validation import CommandKind, RobotCommand  # noqa: E402


class FakePubSub:
    def __init__(self) -> None:
        self.published: list[tuple[int, str]] = []

    def publish_without_callback(self, topic: str, data: dict, msg_type: str = "") -> None:
        self.published.append(
            (data["header"]["identity"]["api_id"], data.get("parameter", ""))
        )

    async def publish_request_new(self, topic: str, demande: dict) -> dict:
        return {"data": {"header": {"status": {"code": 0}}}}


class FakeDataChannel:
    def __init__(self) -> None:
        self.pub_sub = FakePubSub()


class FakeConnexion:
    def __init__(self) -> None:
        self.datachannel = FakeDataChannel()


class FakeSportCmd:
    COMMANDES = {
        "Move": 0x2101,
        "StopMove": 0x2102,
        "StandUp": 0x2103,
        "Sit": 0x2104,
        "Damp": 0x2105,
    }


def build_adapter() -> tuple[WebRTCAdapter, FakeConnexion]:
    adaptateur = WebRTCAdapter(limits=load_limits(), robot_ip="172.16.8.11")
    connexion = FakeConnexion()
    adaptateur._connexion = connexion  # noqa: SLF001 - double de test
    adaptateur._connected = True  # noqa: SLF001
    adaptateur._sport_cmd = FakeSportCmd.COMMANDES  # noqa: SLF001
    adaptateur._rtc = {"SPORT_MOD": "sport-mode"}  # noqa: SLF001
    adaptateur._types_canal = {"REQUEST": "request"}  # noqa: SLF001
    adaptateur._posture = Posture.STAND  # noqa: SLF001
    adaptateur.enable_physical_commands()
    return adaptateur, connexion


def sport_state(
    *,
    code: int = 1013,
    roll: float = 0.0,
    pitch: float = 0.0,
    z: float = 0.32,
) -> dict:
    return {
        "data": {
            "error_code": code,
            "position": [0.0, 0.0, z],
            "velocity": [0.0, 0.0, 0.0],
            "mode": 0,
            "imu_state": {"rpy": [roll, pitch, 0.0]},
        }
    }


def low_state(foot_force: tuple[int, ...] | None = None) -> dict:
    data: dict = {}
    if foot_force is not None:
        data["foot_force"] = list(foot_force)
    return {"data": data}


def commandes(connexion: FakeConnexion) -> list[str]:
    noms = {
        0x2101: "Move",
        0x2102: "StopMove",
        0x2103: "StandUp",
        0x2104: "Sit",
        0x2105: "Damp",
    }
    return [
        noms[api] for api, _ in connexion.datachannel.pub_sub.published if api in noms
    ]


class TestPortage:
    def test_le_robot_soulevé_envoie_un_arret_et_se_verrouille(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        connexion.datachannel.pub_sub.published.clear()

        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))

        assert commandes(connexion) == ["Move", "StopMove", "Damp"]
        assert adaptateur.safety_stop_reason is not None
        assert "soulevé" in adaptateur.safety_stop_reason

    def test_le_verrouillage_est_visible_dans_le_statut(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))
        connexion.datachannel.pub_sub.published.clear()

        statut = _run(adaptateur.get_status())
        assert statut.safety_reason == adaptateur.safety_stop_reason
        assert statut.state is RobotState.ERROR

        # La fin du programme appelle `request_stop` : elle ne doit ni effacer
        # l'état d'erreur, ni renvoyer `Move` après `Damp` (ce qui relèverait
        # le robot).
        _run(adaptateur.request_stop())
        assert _run(adaptateur.get_status()).state is RobotState.ERROR
        assert commandes(connexion) == []

    def test_les_quatre_pieds_charges_ne_declenchent_rien(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state((70, 68, 69, 67)))

        assert commandes(connexion) == []
        assert adaptateur.safety_stop_reason is None

    def test_la_mesure_reelle_au_repos_ne_declenche_pas(self):
        # Relevé le 21/10/2026 sur le Go2 debout : [86, 97, 86, 89], somme 358.
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state((86, 97, 86, 89)))

        assert commandes(connexion) == []
        assert adaptateur.safety_stop_reason is None

    def test_un_robot_assis_avec_pieds_vides_ne_declenche_pas(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state(code=1007, z=0.22))
        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))

        assert commandes(connexion) == []
        assert adaptateur.safety_stop_reason is None

    def test_une_mesure_de_pieds_absente_ne_conclut_pas(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state(None))

        assert commandes(connexion) == []
        assert adaptateur.safety_stop_reason is None

    def test_les_efforts_sont_lus_dans_lowstate(self):
        adaptateur, _ = build_adapter()
        adaptateur._sur_batterie(low_state((70, 68, 69, 67)))

        assert adaptateur._foot_force == (70, 68, 69, 67)  # noqa: SLF001

    def test_une_posture_volontaire_laisse_la_transition_se_terminer(self):
        # Pendant un « s'asseoir » ou un « se coucher », les pieds peuvent se
        # décharger avant que le code d'état ne bascule. Ce n'est pas un
        # portage : la fenêtre de grâce doit empêcher le faux positif.
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._posture_grace_until = time.monotonic() + 5.0  # noqa: SLF001

        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))

        assert commandes(connexion) == []
        assert adaptateur.safety_stop_reason is None

    def test_apres_la_fenetre_de_grâce_un_portage_est_détecté(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._posture_grace_until = time.monotonic() - 1.0  # noqa: SLF001

        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))

        assert commandes(connexion) == ["Move", "StopMove", "Damp"]
        assert adaptateur.safety_stop_reason is not None


class TestInclinaisonIgnoree:
    def test_une_inclinaison_ne_declenche_plus_d_alerte(self):
        # Le relevé de l'IMU pendant un « s'asseoir » puis « se relever »
        # dépasse 45° sans que le robot soit en danger. L'assiette n'est plus
        # un critère d'arrêt : seule la décharge des quatre pieds compte.
        adaptateur, connexion = build_adapter()

        adaptateur._sur_etat(sport_state(roll=math.radians(50)))
        assert adaptateur.safety_stop_reason is None
        adaptateur._sur_etat(sport_state(roll=math.radians(50)))

        assert commandes(connexion) == []
        assert adaptateur.safety_stop_reason is None


class TestCommandesVerrouillees:
    def test_la_preparation_du_programme_est_refusee(self):
        adaptateur, _ = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))

        with pytest.raises(SafetyInterrupt):
            _run(adaptateur.prepare_run())

    def test_une_commande_de_mouvement_est_refusee(self):
        adaptateur, _ = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))

        commande = RobotCommand(
            kind=CommandKind.MOVE_FORWARD, speed=0.2, duration_s=1.0
        )
        with pytest.raises(SafetyInterrupt):
            _run(adaptateur.execute_command(commande, 0, StopSignal()))

    def test_l_arret_reste_toujours_permis(self):
        adaptateur, connexion = build_adapter()
        adaptateur._sur_etat(sport_state())
        adaptateur._sur_batterie(low_state((0, 0, 0, 0)))
        connexion.datachannel.pub_sub.published.clear()

        resultat = _run(
            adaptateur.execute_command(RobotCommand(kind=CommandKind.STOP), 0, StopSignal())
        )

        assert resultat.outcome == "exact"
        # Le déclencheur a déjà envoyé Move/StopMove/Damp ; un second Move
        # relèverait le robot. L'arrêt reste « accepté » sans rien renvoyer.
        assert commandes(connexion) == []


class TestClearanceLidar:
    """La distance libre lue dans la carte, sans robot."""

    def _pret(self) -> WebRTCAdapter:
        adaptateur, _ = build_adapter()
        adaptateur._pose_robot = {"x": 0.0, "y": 0.0, "cap": 0.0}  # noqa: SLF001
        adaptateur._pose_robot_at = time.monotonic()  # noqa: SLF001
        adaptateur._obstacles_lidar = [(1.0, 0.0)]  # noqa: SLF001
        adaptateur._obstacles_lidar_at = time.monotonic()  # noqa: SLF001
        return adaptateur

    def test_un_mur_droit_devant(self):
        adaptateur = self._pret()
        assert _run(adaptateur.clearance_m("forward")) == pytest.approx(0.95)

    def test_securite_desactivee_ne_mesure_plus_la_place(self):
        adaptateur = self._pret()
        adaptateur.obstacle_safety_enabled = False
        assert _run(adaptateur.clearance_m("forward")) is None

    def test_une_action_bloquee_avant_le_premier_pas_n_envoie_aucun_move(self):
        adaptateur, connexion = build_adapter()
        adaptateur._pose_robot = {"x": 0.0, "y": 0.0, "cap": 0.0}  # noqa: SLF001
        adaptateur._pose_robot_at = time.monotonic()  # noqa: SLF001
        adaptateur._obstacles_lidar = [(0.5, 0.0)]  # noqa: SLF001
        adaptateur._obstacles_lidar_at = time.monotonic()  # noqa: SLF001
        plan = plan_command(
            RobotCommand(
                kind=CommandKind.MOVE_FORWARD, speed=0.3, duration_s=5.0
            ),
            adaptateur._limits,  # noqa: SLF001
        )
        assert plan is not None

        resultat = _run(adaptateur._translater(plan, 3, StopSignal()))  # noqa: SLF001

        assert resultat.outcome == "blocked"
        assert resultat.index == 3
        assert "Pas assez de place devant" in (resultat.detail or "")
        assert commandes(connexion) == []

    def test_sans_pose_la_distance_n_est_pas_mesuree(self):
        adaptateur = self._pret()
        adaptateur._pose_robot = None  # noqa: SLF001
        assert _run(adaptateur.clearance_m("forward")) is None

    def test_une_pose_perimee_n_est_pas_utilisee(self):
        adaptateur = self._pret()
        adaptateur._pose_robot_at = time.monotonic() - 5.0  # noqa: SLF001
        assert _run(adaptateur.clearance_m("forward")) is None

    def test_une_carte_perimee_n_est_pas_utilisee(self):
        adaptateur = self._pret()
        adaptateur._obstacles_lidar_at = time.monotonic() - 5.0  # noqa: SLF001
        assert _run(adaptateur.clearance_m("forward")) is None

    def test_le_maillage_3d_retire_le_sol_et_le_plafond(self):
        adaptateur, _ = build_adapter()
        # Un sol de trois cases, un mur à 1 m et 0,50 m de haut, un objet
        # bas, et le plafond. Les positions sont des triplets d'indices,
        # comme les sommets du maillage du SDK.
        donnees = {
            "data": {
                "positions": [
                    0, 0, 0,
                    1, 0, 0,
                    2, 0, 0,
                    20, 0, 10,
                    5, 5, 2,
                    0, 0, 50,
                ]
            },
            "origin": [0.0, 0.0, 0.0],
            "resolution": 0.05,
            "width": [128, 128, 38],
        }

        maillage = adaptateur._maillage_3d(donnees)  # noqa: SLF001

        assert maillage is not None
        assert adaptateur._obstacles_lidar == [(1.0, 0.0)]  # noqa: SLF001
        assert adaptateur._obstacles_lidar_at > 0.0  # noqa: SLF001


def _run(coro):
    import asyncio

    return asyncio.run(coro)
