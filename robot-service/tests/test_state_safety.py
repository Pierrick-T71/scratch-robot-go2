"""Surveillance de portage : décisions pures.

Ces tests n'envoient aucune commande et ne touchent aucun robot. Ils
verrouillent le seuil mesuré (somme des efforts < 60) et les règles de
réarmement : un robot soulevé ne doit pas pouvoir repartir parce qu'un seul
échantillon est revenu à la normale.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.state_safety import SafetySample, StateSafety  # noqa: E402

NOW = 100.0
#: Somme 358 : mesure réelle au repos le 21/10/2026 (docs/ROBOT_SETUP.md).
CHARGÉ = (86, 97, 86, 89)
VIDE = (0, 0, 0, 0)


def sample(
    *,
    now: float = NOW,
    au_sol: bool = False,
    pieds: tuple[int, ...] | None = CHARGÉ,
    pieds_at: float | None = None,
) -> SafetySample:
    return SafetySample(
        now=now,
        au_sol=au_sol,
        foot_force=pieds,
        foot_force_at=now - 0.1 if pieds_at is None and pieds is not None else pieds_at,
    )


class TestPortage:
    def test_les_quatre_pieds_charges_ne_declenchent_rien(self):
        detecteur = StateSafety()
        assert detecteur.update(sample()).tripped is False
        assert detecteur.latched is False

    def test_les_quatre_pieds_vides_declenchent_l_arret(self):
        detecteur = StateSafety()
        evenement = detecteur.update(sample(pieds=VIDE))
        assert evenement.tripped is True
        assert "soulevé" in (evenement.reason or "")
        assert detecteur.latched is True

    def test_le_seuil_est_la_somme_mesuree_de_60(self):
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=(15, 15, 15, 15))).tripped is False
        assert detecteur.update(sample(pieds=(14, 14, 14, 14))).tripped is True

    def test_un_seul_pied_vide_ne_suffit_pas(self):
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=(0, 274, 274, 274))).tripped is False

    def test_une_mesure_incomplete_ou_absente_ne_conclut_pas(self):
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=(0, 0, 0))).tripped is False
        assert detecteur.update(sample(pieds=None, pieds_at=None)).tripped is False

    def test_une_mesure_perimee_ne_declenche_pas(self):
        detecteur = StateSafety()
        perime = sample(pieds=VIDE, pieds_at=NOW - 2.0)
        assert detecteur.update(perime).tripped is False

    def test_assis_ou_allonge_n_est_pas_un_portage(self):
        detecteur = StateSafety()
        # Même avec les pieds à zéro, une posture au sol volontaire ne doit
        # pas être confondue avec un portage.
        assert detecteur.update(sample(au_sol=True, pieds=VIDE)).tripped is False
        assert detecteur.latched is False


class TestRearmement:
    def test_il_faut_une_seconde_d_appuis_stables(self):
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=VIDE)).tripped is True

        # Les appuis reviennent : le verrouillage reste actif le temps de la
        # confirmation.
        assert detecteur.update(sample(now=NOW + 0.1)).cleared is False
        assert detecteur.latched is True
        assert detecteur.update(sample(now=NOW + 1.0)).cleared is False
        assert detecteur.latched is True
        assert detecteur.update(sample(now=NOW + 1.1)).cleared is True
        assert detecteur.latched is False
        assert detecteur.reason is None

    def test_il_peut_rearmer_allonge_apres_un_damp(self):
        # `Damp` relâche les pattes : le robot peut être allongé quand on le
        # repose. Ses pieds chargés suffisent à réarmer ; le programme
        # suivant le relèvera.
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=VIDE)).tripped is True

        assert detecteur.update(sample(now=NOW + 0.1, au_sol=True)).cleared is False
        assert detecteur.latched is True
        assert detecteur.update(sample(now=NOW + 1.1, au_sol=True)).cleared is True
        assert detecteur.latched is False

    def test_une_mesure_absente_ne_rearme_pas(self):
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=VIDE)).tripped is True
        echantillon = SafetySample(now=NOW + 2.0, au_sol=False)
        assert detecteur.update(echantillon).cleared is False
        assert detecteur.latched is True

    def test_apres_rearmement_un_nouveau_portage_redeclenche(self):
        detecteur = StateSafety()
        assert detecteur.update(sample(pieds=VIDE)).tripped is True
        assert detecteur.update(sample(now=NOW + 0.1)).cleared is False
        assert detecteur.update(sample(now=NOW + 1.2)).cleared is True
        assert detecteur.update(sample(now=NOW + 1.3, pieds=VIDE)).tripped is True
