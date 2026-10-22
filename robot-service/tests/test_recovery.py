"""Relevage automatique : le robot allongé se relève si son lidar frotte.

Deux niveaux de tests :

* la **décision** pure (`recovery.py`) : quand faut-il relever ?
* l'**adaptateur** : est-ce que la mesure du lidar est lue comme il faut,
  et est-ce que la commande part ?

Aucun test n'envoie de commande à un vrai robot.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.base import Posture  # noqa: E402
from go2_service.adapters.webrtc import WebRTCAdapter  # noqa: E402
from go2_service.config import load_limits  # noqa: E402
from go2_service.recovery import AutoRecovery, RecoverySample  # noqa: E402

NOW = 100.0


class FakePubSub:
    def __init__(self) -> None:
        self.published: list[tuple[int, str]] = []
        self.requested: list[tuple[int, str]] = []

    def publish_without_callback(self, topic: str, data: dict, msg_type: str = "") -> None:
        self.published.append(
            (data["header"]["identity"]["api_id"], data.get("parameter", ""))
        )

    async def publish_request_new(self, topic: str, demande: dict) -> dict:
        self.requested.append((demande["api_id"], ""))
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
    # Attentes raccourcies : les tests ne doivent pas dormir.
    adaptateur.STABLE_SAMPLE_S = 0.01  # noqa: SLF001
    adaptateur.STABLE_SAMPLES = 2  # noqa: SLF001
    adaptateur.POSTURE_ATTENTE_S = 0.2  # noqa: SLF001
    adaptateur.RELEVER_ATTENTE_S = 0.2  # noqa: SLF001
    adaptateur.RELEVER_REESSAI_S = 0.01  # noqa: SLF001
    adaptateur.PRET_TIMEOUT_S = 0.2  # noqa: SLF001
    return adaptateur, connexion


def sample(
    *,
    now: float = NOW,
    allongé: bool = True,
    lidar_bloque: bool | None = True,
    demande_par_nous: bool = True,
    programme_en_cours: bool = False,
) -> RecoverySample:
    return RecoverySample(
        now=now,
        allongé=allongé,
        lidar_bloque=lidar_bloque,
        demande_par_nous=demande_par_nous,
        programme_en_cours=programme_en_cours,
    )


class TestDecision:
    """Quand faut-il relever ?"""

    def test_allonge_avec_lidar_bloque_declenche_le_relever(self):
        detecteur = AutoRecovery()
        assert detecteur.update(sample(now=NOW)).triggered is False
        assert detecteur.update(sample(now=NOW + 1.1)).triggered is True

    def test_la_confirmation_est_obligatoire(self):
        # Un seul échantillon ne suffit pas : le robot doit être allongé ET
        # le lidar bloqué pendant un moment.
        detecteur = AutoRecovery()
        assert detecteur.update(sample(now=NOW)).triggered is False
        assert detecteur.update(sample(now=NOW + 0.3)).triggered is False
        assert detecteur.update(sample(now=NOW + 0.7)).triggered is True

    def test_un_lidar_libre_ne_declenche_rien(self):
        # C'est le cas le plus fréquent : le chien reste allongé.
        detecteur = AutoRecovery()
        for instant in (NOW, NOW + 0.5, NOW + 1.0, NOW + 5.0):
            assert detecteur.update(sample(now=instant, lidar_bloque=False)).triggered is False

    def test_un_lidar_inconnu_ne_declenche_rien(self):
        detecteur = AutoRecovery()
        for instant in (NOW, NOW + 0.5, NOW + 1.0, NOW + 5.0):
            assert detecteur.update(sample(now=instant, lidar_bloque=None)).triggered is False

    def test_un_robot_tombe_n_est_pas_releve(self):
        # Ce n'est pas nous qui l'avons allongé : le cas visé est le bloc
        # « se coucher ».
        detecteur = AutoRecovery()
        for instant in (NOW, NOW + 0.5, NOW + 1.0, NOW + 5.0):
            assert (
                detecteur.update(
                    sample(now=instant, demande_par_nous=False)
                ).triggered
                is False
            )

    def test_un_programme_en_cours_garde_la_main(self):
        detecteur = AutoRecovery()
        for instant in (NOW, NOW + 0.5, NOW + 1.0, NOW + 5.0):
            assert (
                detecteur.update(
                    sample(now=instant, programme_en_cours=True)
                ).triggered
                is False
            )

    def test_un_robot_debout_n_est_pas_releve(self):
        detecteur = AutoRecovery()
        for instant in (NOW, NOW + 0.5, NOW + 1.0, NOW + 5.0):
            assert (
                detecteur.update(sample(now=instant, allongé=False)).triggered is False
            )

    def test_une_situation_interrompue_redemarre_la_confirmation(self):
        detecteur = AutoRecovery()
        assert detecteur.update(sample(now=NOW)).triggered is False
        # Le lidar se libère : la confirmation repart de zéro.
        assert detecteur.update(sample(now=NOW + 0.5, lidar_bloque=False)).triggered is False
        assert detecteur.update(sample(now=NOW + 1.0)).triggered is False
        assert detecteur.update(sample(now=NOW + 2.0)).triggered is True


class TestMesureDuLidar:
    """La mesure vient de l'état du lidar (`rt/utlidar/lidar_state`).

    Le critère est la **rotation réelle** : quand la fenêtre du lidar frotte
    contre le sol, le moteur force et la rotation chute.

    ⚠️ Le `dirty_percentage` n'est PAS un indice de blocage : mesuré le
    21/10/2026, il vaut 61-70 % quand le chien est allongé alors que le
    lidar tourne librement.
    """

    #: Rotation normale du lidar, mesurée sur le robot réel le 21/10/2026.
    NORMAL = 0.02025

    def etat(self, com: float, sys: float = 12917.0, **extra) -> dict:
        donnees = {
            "error_state": 0,
            "dirty_percentage": 63,
            "sys_rotation_speed": sys,
            "com_rotation_speed": com,
        }
        donnees.update(extra)
        return donnees

    def _remplir(self, adaptateur, com: float, fois: int = 20) -> None:
        """Alimente l'historique de rotation avec des mesures normales."""
        for _ in range(fois):
            adaptateur._sur_etat_lidar(self.etat(com))  # noqa: SLF001

    def test_un_lidar_qui_tourne_normalement_n_est_pas_bloque(self):
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        assert adaptateur._lidar_bloque() is False  # noqa: SLF001

    def test_un_lidar_qui_ralentit_est_bloque(self):
        # Mesure réelle du 21/10/2026 : 0,0114 quand le lidar frotte le
        # sol, contre 0,0203 en temps normal (soit 0,56 de la médiane).
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        adaptateur._sur_etat_lidar(self.etat(147.0))  # noqa: SLF001
        assert adaptateur._lidar_bloque() is True  # noqa: SLF001

    def test_un_lidar_qui_accelere_est_bloque(self):
        # Autre forme du blocage, mesurée le 21/10/2026 à 14:14 : le
        # contrôleur du lidar change de régime et la rotation monte à
        # 0,0334 (1,64 de la médiane). Le blocage doit être vu dans les
        # DEUX sens.
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        adaptateur._sur_etat_lidar(self.etat(439.8))  # noqa: SLF001
        assert adaptateur._lidar_bloque() is True  # noqa: SLF001

    def test_un_blocage_durable_ne_deplace_pas_la_reference(self):
        # Si les mesures de blocage entraient dans l'historique, la médiane
        # monterait et le détecteur s'éteindrait de lui-même.
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        for _ in range(60):
            adaptateur._sur_etat_lidar(self.etat(439.8))  # noqa: SLF001
            assert adaptateur._lidar_bloque() is True  # noqa: SLF001

    def test_un_pic_de_mesure_ne_bouge_pas_l_echelle(self):
        # Un pic a été mesuré (0,0729) pendant une pose. Avec une échelle
        # bâtie sur le maximum, tout aurait ensuite semblé « bloqué ».
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        adaptateur._sur_etat_lidar(self.etat(940.0))  # noqa: SLF001 - le pic
        # Le lidar tourne normalement : ce n'est PAS bloqué.
        adaptateur._sur_etat_lidar(self.etat(261.8))  # noqa: SLF001
        assert adaptateur._lidar_bloque() is False  # noqa: SLF001

    def test_un_relèvement_ne_ressemble_pas_a_un_blocage(self):
        # Mesuré : 0,0182 pendant un relèvement, soit 0,90 de la médiane.
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        adaptateur._sur_etat_lidar(self.etat(235.0))  # noqa: SLF001
        assert adaptateur._lidar_bloque() is False  # noqa: SLF001

    def test_une_erreur_firmware_signale_un_lidar_bloque(self):
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        adaptateur._sur_etat_lidar(  # noqa: SLF001
            self.etat(261.8, error_state=3)
        )
        assert adaptateur._lidar_bloque() is True  # noqa: SLF001

    def test_sans_etat_du_lidar_on_ne_conclut_pas(self):
        adaptateur, _ = build_adapter()
        assert adaptateur._lidar_bloque() is None  # noqa: SLF001

    def test_avec_trop_peu_de_mesures_on_ne_conclut_pas(self):
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8, fois=3)
        assert adaptateur._lidar_bloque() is None  # noqa: SLF001

    def test_un_etat_perime_ne_conclut_pas(self):
        adaptateur, _ = build_adapter()
        self._remplir(adaptateur, 261.8)
        adaptateur._etat_lidar_at = time.monotonic() - 60  # noqa: SLF001
        assert adaptateur._lidar_bloque() is None  # noqa: SLF001


class TestAdaptateur:
    """L'adaptateur envoie la commande, et seulement dans le bon cas."""

    @pytest.mark.asyncio
    async def test_le_coucher_arme_le_relever_automatiquement(self):
        adaptateur, _ = build_adapter()
        await adaptateur._do_geste("Damp", 0)  # noqa: SLF001 - « se coucher »
        assert adaptateur._allonge_demande is True  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_le_relever_part_quand_le_lidar_est_bloque(self):
        adaptateur, connexion = build_adapter()
        adaptateur._allonge_demande = True  # noqa: SLF001
        adaptateur._code_etat = 1001  # noqa: SLF001 - allongé par terre
        normal = {
            "error_state": 0,
            "dirty_percentage": 63,
            "sys_rotation_speed": 12917.0,
            "com_rotation_speed": 261.8,
        }
        for _ in range(20):
            adaptateur._sur_etat_lidar(normal)  # noqa: SLF001
        # Le lidar frotte le sol : sa rotation chute (mesure du 21/10/2026).
        ralenti = dict(normal)
        ralenti["com_rotation_speed"] = 147.0
        adaptateur._sur_etat_lidar(ralenti)  # noqa: SLF001
        connexion.datachannel.pub_sub.published.clear()

        # On force la confirmation : le test ne doit pas dormir une seconde.
        adaptateur._relever_auto.confirm_s = 0.0  # noqa: SLF001
        instant = time.monotonic()
        adaptateur._examiner_relever(instant)  # noqa: SLF001
        adaptateur._examiner_relever(instant + 0.3)  # noqa: SLF001
        await asyncio.sleep(0.2)
        tache = adaptateur._tache_relever  # noqa: SLF001
        assert tache is not None
        await tache

        # La commande de relèvement est bien partie.
        noms = {
            0x2101: "Move",
            0x2102: "StopMove",
            0x2103: "StandUp",
            0x2104: "Sit",
            0x2105: "Damp",
        }
        demandees = [
            noms[api]
            for api, _ in connexion.datachannel.pub_sub.requested
            if api in noms
        ]
        assert "StandUp" in demandees

    @pytest.mark.asyncio
    async def test_aucune_commande_tant_que_le_lidar_tourne(self):
        adaptateur, connexion = build_adapter()
        adaptateur._allonge_demande = True  # noqa: SLF001
        adaptateur._code_etat = 1001  # noqa: SLF001
        # Le chien est allongé, mais le lidar tourne normalement : rien à
        # faire. C'est le cas le plus fréquent.
        for _ in range(20):
            adaptateur._sur_etat_lidar(  # noqa: SLF001
                {
                    "error_state": 0,
                    "dirty_percentage": 63,
                    "sys_rotation_speed": 12917.0,
                    "com_rotation_speed": 261.8,
                }
            )
        connexion.datachannel.pub_sub.published.clear()

        adaptateur._relever_auto.confirm_s = 0.0  # noqa: SLF001
        instant = time.monotonic()
        adaptateur._examiner_relever(instant)  # noqa: SLF001
        adaptateur._examiner_relever(instant + 0.3)  # noqa: SLF001
        await asyncio.sleep(0.2)

        assert adaptateur._tache_relever is None  # noqa: SLF001
        assert connexion.datachannel.pub_sub.published == []
