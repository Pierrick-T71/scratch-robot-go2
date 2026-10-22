"""Surveillance du portage du robot.

RAISON D'ÊTRE
-------------
Un Go2 peut être soulevé alors qu'il marche. Continuer à lui envoyer une
consigne de vitesse est dangereux : les pattes battent dans le vide, et le
robot peut repartir dès qu'il retrouve un appui.

Ce module ne commande RIEN. Il transforme une mesure en une décision :
« il faut s'arrêter » ou « le robot peut être réarmé ». L'adaptateur WebRTC
reste seul responsable de l'envoi de l'arrêt, et le moteur d'exécution de la
fin du programme.

MESURES UTILISÉES
-----------------
* `foot_force`, publié par `rt/lf/lowstate` : quatre valeurs entières. Au
  repos, les quatre pieds portent (somme relevée entre **274** pendant les
  essais de saut et **360** à la connexion du 21/10/2026). `docs/ROBOT_SETUP.md`
  et `.setup/test_sauts3.py` retiennent « les pieds ne portent plus » quand
  leur SOMME passe sous 60.

LIMITES ASSUMÉES
----------------
* Un pied au-dessus d'un vide alors que les trois autres portent n'est PAS
  détecté : `foot_force` ne dit pas où est le sol.
* Un robot allongé ou assis a normalement peu ou pas d'appui dans les pieds :
  ces postures sont donc exclues de la détection de portage. Après un arrêt
  de sécurité suivi de `Damp`, le robot peut être réarmé dès que ses pieds
  portent de nouveau, même allongé ; le programme suivant le relèvera.
* Sans `foot_force` frais, aucun portage n'est détecté. On ne remplace jamais
  une mesure absente par une valeur favorable.
* Ce module ne remplace ni la télécommande, ni la surveillance d'un adulte.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Somme des quatre efforts sous laquelle les pieds ne portent plus.
#: Origine : mesure consignée dans `docs/ROBOT_SETUP.md` et seuil utilisé par
#: `.setup/test_sauts3.py` (`t < 60`).
FOOT_FORCE_MIN_TOTAL = 60

#: Nombre d'échantillons consécutifs avant de conclure.
#:
#: Le portage est conclu dès le premier échantillon complet à zéro : les
#: quatre pieds simultanément déchargés sont un signal sans ambiguïté, et le
#: flux basse fréquence ne permet pas d'attendre.
AIRBORNE_CONFIRM_SAMPLES = 1

#: Durée minimale d'appuis revenus avant réarmement.
RECOVERY_STABLE_S = 1.0

#: Au-delà de cette ancienneté, une mesure n'est plus utilisée.
SENSOR_STALE_S = 1.0

_AIRBORNE_REASON = (
    "Le robot a été soulevé : il s’est arrêté et a relâché ses pattes. "
    "Repose-le au sol et attends qu’il soit stable."
)


@dataclass(frozen=True)
class SafetySample:
    """Un instant de mesure, déjà horodaté par l'adaptateur."""

    now: float
    #: Le robot est assis ou allongé : ses pieds ne portent pas normalement.
    au_sol: bool
    foot_force: tuple[int, ...] | None = None
    foot_force_at: float | None = None


@dataclass(frozen=True)
class SafetyEvent:
    """Décision rendue après un échantillon."""

    tripped: bool = False
    cleared: bool = False
    reason: str | None = None


class StateSafety:
    """Détecte un portage, avec verrouillage.

    Le verrouillage est volontaire : une fois déclenché, il ne se lève que
    lorsque les quatre pieds portent de nouveau depuis une seconde. Après un
    `Damp`, le robot peut être allongé : ses pieds peuvent porter, et le
    programme suivant le relèvera.
    """

    def __init__(
        self,
        *,
        foot_force_min_total: int = FOOT_FORCE_MIN_TOTAL,
        airborne_confirm_samples: int = AIRBORNE_CONFIRM_SAMPLES,
        recovery_stable_s: float = RECOVERY_STABLE_S,
        sensor_stale_s: float = SENSOR_STALE_S,
    ) -> None:
        self.foot_force_min_total = foot_force_min_total
        self.airborne_confirm_samples = max(1, airborne_confirm_samples)
        self.recovery_stable_s = max(0.0, recovery_stable_s)
        self.sensor_stale_s = max(0.0, sensor_stale_s)

        self._latched = False
        self._reason: str | None = None
        self._airborne_count = 0
        self._safe_since: float | None = None

    @property
    def latched(self) -> bool:
        """Un arrêt de sécurité est-il actif ?"""
        return self._latched

    @property
    def reason(self) -> str | None:
        """Raison destinée à l'interface, ou `None` si rien n'est armé."""
        return self._reason

    def reset(self) -> None:
        """Oublie un verrouillage. Réservé aux tests et à une reconnexion."""
        self._latched = False
        self._reason = None
        self._airborne_count = 0
        self._safe_since = None

    def update(self, sample: SafetySample) -> SafetyEvent:
        """Analyse un échantillon et rend la décision correspondante.

        Ne lève jamais : une mesure illisible ou absente vaut « inconnue »,
        jamais « le robot est en sécurité ».
        """
        if self._latched:
            return self._update_latched(sample)

        # Assis ou allongé : les pieds ne portent pas normalement. On ne
        # confond pas cette posture volontaire avec un portage.
        if sample.au_sol:
            self._airborne_count = 0
            return SafetyEvent()

        airborne = self._airborne(sample)
        self._airborne_count = (
            self._airborne_count + 1 if airborne is True else 0
        )

        if self._airborne_count >= self.airborne_confirm_samples:
            return self._trip(_AIRBORNE_REASON)
        return SafetyEvent()

    # -- Décisions internes -------------------------------------------------

    def _update_latched(self, sample: SafetySample) -> SafetyEvent:
        if not self._safe_to_rearm(sample):
            self._safe_since = None
            return SafetyEvent()

        if self._safe_since is None:
            self._safe_since = sample.now
            return SafetyEvent()

        if sample.now - self._safe_since >= self.recovery_stable_s:
            self._latched = False
            self._reason = None
            self._airborne_count = 0
            self._safe_since = None
            return SafetyEvent(cleared=True)
        return SafetyEvent()

    def _trip(self, reason: str) -> SafetyEvent:
        self._latched = True
        self._reason = reason
        self._safe_since = None
        return SafetyEvent(tripped=True, reason=reason)

    def _safe_to_rearm(self, sample: SafetySample) -> bool:
        """Les quatre pieds portent-ils de nouveau ?

        La posture n'est pas exigée : après un `Damp`, le robot est allongé
        et ne peut pas se relever seul. Le programme suivant s'en charge.
        Une mesure absente ne réarme jamais.
        """
        return self._airborne(sample) is False

    def _airborne(self, sample: SafetySample) -> bool | None:
        """`True` si les quatre pieds sont déchargés, `None` si non mesuré."""
        if sample.foot_force is None or sample.foot_force_at is None:
            return None
        if sample.now - sample.foot_force_at > self.sensor_stale_s:
            return None
        if len(sample.foot_force) != 4:
            return None
        return sum(sample.foot_force) < self.foot_force_min_total
