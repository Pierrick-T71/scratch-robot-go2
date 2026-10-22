"""Relevage automatique : le robot qui s'est allongé se relève tout seul.

RAISON D'ÊTRE
-------------
Le lidar du Go2 est monté **devant la tête**. Quand le chien est allongé,
la tête est au niveau du sol : la fenêtre tournante du lidar frotte le
sol, et le robot force contre elle. Le chien s'use, et l'application ne
peut plus rien voir (la carte du lidar est illisible).

Le cas visé est le bloc « se coucher » : le robot a été allongé **par
nous**, il reste couché, et son lidar se coince. Dans ce cas précis, il
doit se relever tout seul.

Ce module ne commande RIEN. Il transforme des mesures en une décision :
« le robot doit se relever » ou non. L'adaptateur WebRTC reste seul
responsable de l'envoi de `RecoveryStand`.

MESURES UTILISÉES
-----------------
* l'état publié par le robot : `1001` = allongé par terre ;
* **le lidar est-il bloqué ?** C'est LA condition : tant que le lidar
  tourne librement, le chien reste allongé, comme l'enfant l'a demandé ;
* le fait qu'aucun programme ne soit en cours : pendant un programme,
  c'est lui qui prépare le robot (`prepare_run` le relève).

LIMITES ASSUMÉES
----------------
* sans mesure du lidar, aucune décision n'est prise ;
* un robot **tombé** n'est pas relevé : ce n'est pas le cas visé ici, et
  relever un chien tombé peut être dangereux (il peut retomber) ;
* le relevé est une **manœuvre physique** : il échoue si l'espace autour
  du robot est obstrué. Le chien reste alors allongé, et c'est l'adulte
  qui doit le redresser.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Durée pendant laquelle la situation doit être confirmée avant de relever.
#:
#: Assez long pour ne pas réagir à un pic de mesure isolé (on en a vu un de
#: 2 ms au moment où le chien s'allonge), assez court pour que le chien ne
#: reste pas longtemps avec son lidar contre le sol.
CONFIRM_S = 0.6

_REASON = (
    "Le robot s’est allongé et son lidar frotte le sol : il se relève tout seul."
)


@dataclass(frozen=True)
class RecoverySample:
    """Un instant de mesure, déjà horodaté par l'adaptateur."""

    now: float
    #: Le robot est allongé par terre (code d'état `1001`).
    allongé: bool
    #: Le lidar est-il bloqué contre le sol ? `None` = on ne sait pas.
    lidar_bloque: bool | None = None
    #: Avons-nous demandé nous-mêmes cet allongement ? (bloc « se coucher »)
    demande_par_nous: bool = False
    #: Un programme est-il en cours ?
    programme_en_cours: bool = False


@dataclass(frozen=True)
class RecoveryEvent:
    """Décision rendue après un échantillon."""

    triggered: bool = False
    reason: str | None = None


class AutoRecovery:
    """Décide quand un robot allongé doit se relever tout seul.

    Le déclencheur est volontairement strict : un faux positif fait lever un
    robot au mauvais moment, un faux négatif laisse un chien allongé avec
    son lidar contre le sol. Dans le doute, on ne fait rien.
    """

    def __init__(self, *, confirm_s: float = CONFIRM_S) -> None:
        self.confirm_s = max(0.0, confirm_s)
        self._depuis: float | None = None

    def reset(self) -> None:
        """Oublie la confirmation en cours."""
        self._depuis = None

    def update(self, sample: RecoverySample) -> RecoveryEvent:
        """Analyse un échantillon et rend la décision correspondante."""
        if not self._a_relever(sample):
            self._depuis = None
            return RecoveryEvent()

        if self._depuis is None:
            self._depuis = sample.now
            return RecoveryEvent()

        if sample.now - self._depuis >= self.confirm_s:
            self._depuis = None
            return RecoveryEvent(triggered=True, reason=_REASON)
        return RecoveryEvent()

    # -- Décisions internes -------------------------------------------------

    def _a_relever(self, sample: RecoverySample) -> bool:
        if not sample.allongé:
            return False
        if not sample.demande_par_nous:
            # Ce n'est pas nous qui l'avons allongé : le cas visé est le
            # bloc « se coucher ».
            return False
        if sample.lidar_bloque is not True:
            # Le lidar tourne librement : le chien peut rester allongé.
            return False
        if sample.programme_en_cours:
            # Un programme est en train : c'est lui qui relève le robot.
            return False
        return True
