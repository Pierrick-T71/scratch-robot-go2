"""Posture du robot : rester assis, repartir sur quatre pattes.

Deux points importants, observés sur le robot réel :

  1. « S'asseoir » en fin de programme doit DURER. Or une consigne `Move`
     envoyée à un Go2 assis le relève : l'arrêt de fin de programme
     annulait donc la posture demandée, et l'enfant voyait le robot se
     relever aussitôt.

  2. Un programme doit toujours commencer avec le robot SUR SES QUATRE
     PATTES. S'il est resté assis (fin de programme précédente, test de
     liaison), il se relève tout seul, avant le premier ordre.

Ces tests vérifient les ENVOIS faits au canal, pas l'opinion du service.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.base import Posture  # noqa: E402
from go2_service.adapters.webrtc import WebRTCAdapter  # noqa: E402
from go2_service.config import load_limits  # noqa: E402


class FakePubSub:
    """Enregistre les publications, sans répondre comme le robot."""

    def __init__(self, code: int = 0, codes: list[int] | None = None) -> None:
        self.code = code
        self.codes = list(codes) if codes else None
        self.published: list[tuple[str, str]] = []
        self.requested: list[tuple[str, str]] = []

    def publish_without_callback(self, topic: str, data: dict, msg_type: str = "") -> None:
        self.published.append((data["header"]["identity"]["api_id"], data.get("parameter", "")))

    async def publish_request_new(self, topic: str, demande: dict) -> dict:
        self.requested.append((demande["api_id"], ""))
        code = self.code
        if self.codes:
            code = self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]
        return {"data": {"header": {"status": {"code": code}}}}


class FakeDataChannel:
    def __init__(self, code: int = 0, codes: list[int] | None = None) -> None:
        self.pub_sub = FakePubSub(code, codes)


class FakeConnexion:
    def __init__(self, code: int = 0, codes: list[int] | None = None) -> None:
        self.datachannel = FakeDataChannel(code, codes)


class FakeSportCmd:
    """Table des identifiants de commande, comme le SDK les expose."""

    COMMANDES = {
        "Move": 0x2101,
        "StopMove": 0x2102,
        "StandUp": 0x2103,
        "Sit": 0x2104,
    }


def build_adapter(code: int = 0, codes: list[int] | None = None) -> tuple[WebRTCAdapter, FakeConnexion]:
    adaptateur = WebRTCAdapter(limits=load_limits(), robot_ip="172.16.8.11")
    connexion = FakeConnexion(code, codes)
    adaptateur._connexion = connexion  # noqa: SLF001 - double de test
    adaptateur._connected = True  # noqa: SLF001
    adaptateur._sport_cmd = FakeSportCmd.COMMANDES  # noqa: SLF001
    adaptateur._rtc = {"SPORT_MOD": "sport-mode"}  # noqa: SLF001
    adaptateur._types_canal = {"REQUEST": "request"}  # noqa: SLF001
    # Attentes raccourcies : les tests ne doivent pas dormir trois secondes.
    adaptateur.STABLE_SAMPLE_S = 0.01  # noqa: SLF001
    adaptateur.STABLE_SAMPLES = 2  # noqa: SLF001
    return adaptateur, connexion


def commandes(connexion: FakeConnexion) -> list[str]:
    noms = {0x2101: "Move", 0x2102: "StopMove", 0x2103: "StandUp", 0x2104: "Sit"}
    return [noms[api] for api, _ in connexion.datachannel.pub_sub.published]


def consignes_de_vitesse(connexion: FakeConnexion) -> list[str]:
    """Les parametres des `Move` envoyes, pour verifier qu'ils sont nuls."""
    return [
        parametre
        for api, parametre in connexion.datachannel.pub_sub.published
        if api == 0x2101
    ]


def commandes_demandees(connexion: FakeConnexion) -> list[str]:
    noms = {0x2101: "Move", 0x2102: "StopMove", 0x2103: "StandUp", 0x2104: "Sit"}
    return [noms[api] for api, _ in connexion.datachannel.pub_sub.requested]


class TestArret:
    """L'arrêt ne doit pas contredire la posture demandée."""

    @pytest.mark.asyncio
    async def test_un_robot_assis_ne_releve_pas_a_l_arret(self):
        # Sur un Go2, `Move` ET `StopMove` relèvent le robot. Assis, on
        # n'envoie donc RIEN : il n'y a aucun mouvement à annuler.
        adaptateur, connexion = build_adapter()
        adaptateur._posture = Posture.SIT  # noqa: SLF001

        await adaptateur.request_stop()

        assert commandes(connexion) == []
        assert commandes_demandees(connexion) == []

    @pytest.mark.asyncio
    async def test_un_robot_debout_reoit_la_consigne_nulle(self):
        adaptateur, connexion = build_adapter()
        adaptateur._posture = Posture.STAND  # noqa: SLF001

        await adaptateur.request_stop()

        assert commandes(connexion) == ["Move", "StopMove"]


class TestPostureMesuree:
    """La hauteur lue dans l'état dit si le robot est assis."""

    def test_un_robot_bas_est_assis(self):
        adaptateur, _ = build_adapter()
        adaptateur._position = (0.0, 0.0, 0.222)  # noqa: SLF001
        adaptateur._hauteur_max = 0.327  # noqa: SLF001
        assert adaptateur._est_assis() is True

    def test_un_robot_haut_est_debout(self):
        adaptateur, _ = build_adapter()
        adaptateur._position = (0.0, 0.0, 0.327)  # noqa: SLF001
        adaptateur._hauteur_max = 0.327  # noqa: SLF001
        assert adaptateur._est_assis() is False

    def test_le_code_d_etat_prime_sur_la_hauteur(self):
        # Le robot publie 1007 quand il est assis : c'est plus fiable que
        # la hauteur, qui bouge pour d'autres raisons.
        adaptateur, _ = build_adapter()
        adaptateur._code_etat = 1007  # noqa: SLF001
        adaptateur._position = (0.0, 0.0, 0.327)  # noqa: SLF001
        adaptateur._hauteur_max = 0.327  # noqa: SLF001
        assert adaptateur._est_assis() is True

    def test_sans_mesure_on_suit_le_dernier_ordre(self):
        adaptateur, _ = build_adapter()
        adaptateur._position = None  # noqa: SLF001
        adaptateur._posture = Posture.SIT  # noqa: SLF001
        assert adaptateur._est_assis() is True

    def test_sans_mesure_ni_ordre_on_ne_presume_pas_que_ce_soit_debout(self):
        # Ni l'etat du robot, ni la mesure, ni le dernier ordre : on ne
        # suppose pas que le robot soit debout. Le service le relèvera.
        adaptateur, _ = build_adapter()
        adaptateur._position = None  # noqa: SLF001
        adaptateur._posture = None  # noqa: SLF001
        assert adaptateur._est_debout() is False
        assert adaptateur._est_assis() is False

    def test_un_robot_alleonge_est_detecte(self):
        adaptateur, _ = build_adapter()
        adaptateur._code_etat = 1001  # noqa: SLF001
        adaptateur._position = (0.0, 0.0, 0.053)  # noqa: SLF001
        adaptateur._hauteur_max = 0.327  # noqa: SLF001
        assert adaptateur._est_alleonge() is True
        assert adaptateur._est_assis() is False

    def test_un_bond_ne_pollue_pas_la_hauteur_de_reference(self):
        # Pendant un mouvement violent, l'odometrie s'emballe. Cette
        # hauteur-la ne doit PAS devenir la reference « debout » : sinon
        # le service Croira que le robot ne peut plus etre debout.
        adaptateur, _ = build_adapter()
        adaptateur._code_etat = 100  # en mouvement
        adaptateur._position = (0.0, 0.0, 0.52)  # noqa: SLF001
        adaptateur._hauteur_max = 0.327  # noqa: SLF001
        assert adaptateur._est_debout() is True


class TestEtatPret:
    """Le robot n'obéit pas aux mouvements pendant une transition.

    Mesure faite sur la machine : le code d'état `1002` signifie
    « transition de posture en cours ». Pendant ce temps, le robot IGNORE
    les consignes `Move` — et les lui envoyer empêche même la transition
    de se terminer.
    """

    @pytest.mark.asyncio
    async def test_le_robot_est_pret_quand_il_publie_100(self):
        adaptateur, _ = build_adapter()
        adaptateur._code_etat = 100  # noqa: SLF001
        assert await adaptateur._attendre_pret() is True

    @pytest.mark.asyncio
    async def test_une_transition_ne_finit_pas_toute_seule(self):
        adaptateur, _ = build_adapter()
        adaptateur._code_etat = 1002  # noqa: SLF001
        adaptateur.PRET_TIMEOUT_S = 0.05  # noqa: SLF001
        assert await adaptateur._attendre_pret() is False

    @pytest.mark.asyncio
    async def test_aucune_consigne_de_mouvement_pendant_une_transition(self):
        from go2_service.adapters.base import AdapterError
        from go2_service.validation import CommandKind, RobotCommand

        adaptateur, connexion = build_adapter()
        adaptateur._code_etat = 1002  # noqa: SLF001
        adaptateur.PRET_TIMEOUT_S = 0.05  # noqa: SLF001

        commande = RobotCommand(
            kind=CommandKind.MOVE_FORWARD, speed=0.3, duration_s=2
        )
        with pytest.raises(AdapterError, match="prêt"):
            await adaptateur._do_move(commande, 0, None)  # noqa: SLF001

        # Pendant une transition, seule une consigne NULLE peut partir :
        # c'est elle qui fait sortir le robot de sa transition. Aucune
        # consigne de mouvement reel ne doit etre envoyee.
        for parametre in consignes_de_vitesse(connexion):
            assert '"x": 0.0' in parametre
            assert '"x": 0.3' not in parametre


class TestPreparationDuProgramme:
    """Le robot doit être debout au premier ordre."""

    @pytest.mark.asyncio
    async def test_un_robot_assis_se_releve_avant_le_programme(self):
        adaptateur, connexion = build_adapter()
        adaptateur._posture = Posture.SIT  # noqa: SLF001

        await adaptateur.prepare_run()

        assert commandes_demandees(connexion) == ["StandUp"]
        assert adaptateur._posture is Posture.STAND  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_un_robot_debout_n_est_pas_relance(self):
        adaptateur, connexion = build_adapter()
        adaptateur._posture = Posture.STAND  # noqa: SLF001

        await adaptateur.prepare_run()

        assert commandes_demandees(connexion) == []

    @pytest.mark.asyncio
    async def test_un_robot_de_posture_inconnue_est_relance(self):
        # On ne sait pas dans quelle posture il est : on le met debout.
        adaptateur, connexion = build_adapter()
        adaptateur._posture = None  # noqa: SLF001

        await adaptateur.prepare_run()

        assert commandes_demandees(connexion) == ["StandUp"]
        assert adaptateur._posture is Posture.STAND  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_un_relèvement_refusé_ne_leve_pas(self):
        adaptateur, connexion = build_adapter(code=1)
        adaptateur._posture = Posture.SIT  # noqa: SLF001

        await adaptateur.prepare_run()

        # La commande a bien été tentée, mais le service ne pretendant pas
        # que le robot est debout, il ne note pas la posture.
        assert commandes_demandees(connexion) == ["StandUp"]
        assert adaptateur._posture is Posture.SIT  # noqa: SLF001


class TestPostureRefusee:
    """Le robot refuse une posture pendant une transition.

    C'est ce qui faisait que « s'asseoir » demandé juste après un
    « se relever » n'était jamais exécuté : le robot se relevait, et
    l'enfant croyait que son ordre avait été obéi.
    """

    @pytest.mark.asyncio
    async def test_une_posture_refusee_est_reessayee_une_fois(self):
        adaptateur, connexion = build_adapter(codes=[1, 0])
        # Une hauteur stable : le robot est immobile, on peut réessayer.
        adaptateur._position = (0.0, 0.0, 0.30)  # noqa: SLF001

        resultat = await adaptateur._do_posture("Sit", Posture.SIT, 0)  # noqa: SLF001

        assert commandes_demandees(connexion) == ["Sit", "Sit"]
        assert resultat.outcome == "exact"
        assert adaptateur._posture is Posture.SIT  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_un_second_refus_est_signale(self):
        adaptateur, connexion = build_adapter(codes=[1, 1])
        adaptateur._position = (0.0, 0.0, 0.30)  # noqa: SLF001

        resultat = await adaptateur._do_posture("Sit", Posture.SIT, 0)  # noqa: SLF001

        assert commandes_demandees(connexion) == ["Sit", "Sit"]
        assert resultat.outcome == "failed"
        assert "refusé" in (resultat.detail or "")
