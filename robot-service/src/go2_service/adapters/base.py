"""Contrat interne `RobotAdapter`.

Ce sont des contrats du PROJET, pas des méthodes fournies par Unitree. Le
service ne connaît QUE cette interface, ce qui permet de changer de version
du SDK sans toucher à l'éditeur Blockly ni au moteur d'exécution.

Capacités volontairement MINIMALES. Toute commande non couverte doit être
refusée explicitement par l'adaptateur, jamais improvisée.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from ..validation import Capability, RobotCommand


class AdapterError(RuntimeError):
    """L'adaptateur ne peut pas exécuter la demande.

    `recoverable` distingue une panne temporaire (reconnexion possible) d'un
    refus définitif.
    """

    def __init__(self, message: str, *, recoverable: bool = False) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class SafetyInterrupt(AdapterError):
    """Le robot s'est arrêté de lui-même pour une raison de sécurité.

    Distinct d'une panne : l'arrêt est VOULU. Le moteur d'exécution le traduit
    en fin de programme « safety », et non en erreur technique.
    """


class Posture(str, Enum):
    """Postures exposées aux enfants."""

    STAND = "stand"
    SIT = "sit"
    LIE_DOWN = "lie_down"
    BALANCE = "balance"


class RobotState(str, Enum):
    """ États observables, sans interprétation optimiste.

    `unknown` est volontairement distinct de `idle` : le service ne doit
    jamais supposer que le robot est prêt quand il ne connaît pas son état.
    """

    UNKNOWN = "unknown"
    IDLE = "idle"
    MOVING = "moving"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class Status:
    """État du robot tel que connu par le service."""

    connected: bool
    state: RobotState
    capabilities: frozenset[Capability]
    blocked_reason: str | None = None
    position_m: tuple[float, float, float] | None = None
    yaw_rad: float | None = None
    battery_percent: float | None = None
    posture: Posture | None = None
    #: Mesure ou raison d'un arrêt de sécurité détecté par l'adaptateur.
    #: `None` quand aucun arrêt de ce type n'est armé.
    safety_reason: str | None = None
    #: Message du relevé automatique (le robot s'est relevé tout seul, ou
    #: n'a pas réussi). `None` quand rien ne s'est passé.
    recovery_reason: str | None = None


@dataclass(frozen=True)
class CommandOutcome:
    """Résultat d'une instruction.

    `measured` ne contient des valeurs que si l'adaptateur les a
    RÉELLEMENT lues dans l'état du robot. Il ne doit jamais être renseigné
    avec la valeur théorique demandée : c'est ce qui permet à l'interface de
    distinguer « terminé » de « temps écoulé ».
    """

    index: int
    #: `exact` = cible atteinte d'après l'état mesuré.
    #: `timeout` = délai atteint sans confirmation mesurée.
    #: `stopped` = interrompu sur demande, ou par un obstacle apparu.
    #: `blocked` = action NON faite : la place libre ne suffisait pas.
    #: Le programme continue avec l'instruction suivante.
    #: `failed` = erreur de l'adaptateur.
    outcome: Literal["exact", "timeout", "stopped", "blocked", "failed"]
    measured_distance_cm: float | None = None
    measured_angle_deg: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MotionPlan:
    """Traduction interne d'un déplacement, indépendante du SDK.

    Consigne de vitesse + durée nominale. Le service ne présente JAMAIS la
    durée nominale comme une garantie d'arrivée.
    """

    linear_speed_mps: float
    angular_speed_rps: float
    nominal_duration_s: float
    timeout_s: float
    #: Vitesse latérale (`vy` de `Move(vx, vy, vyaw)`). 0 pour un déplacement
    #: avant/arrière, et pour une rotation.
    lateral_speed_mps: float = 0.0
    distance_cm: float = 0.0
    angle_deg: float = 0.0


@runtime_checkable
class RobotAdapter(Protocol):
    """Interface que tout adaptateur doit respecter."""

    name: str
    #: `False` tant que l'intégration physique n'a pas été validée.
    physical_commands_enabled: bool

    async def connect(self) -> None:
        """Établit la liaison. Lève `AdapterError` en cas d'échec."""
        ...

    async def disconnect(self) -> None:
        """Ferme la liaison de façon propre."""
        ...

    async def get_status(self) -> Status:
        """État courant. Ne doit jamais lever : retourne `state=unknown`."""
        ...

    async def execute_command(
        self, command: RobotCommand, index: int, should_stop: "StopSignal"
    ) -> CommandOutcome:
        """Exécute une instruction jusqu'à son terme.

        `should_stop` est un objet partagé : l'appelant peut le déclencher à
        tout moment (bouton Arrêter, bail expiré, dépassement de durée).
        L'adaptateur DOIT surveiller ce signal pendant toute la durée de
        l'instruction et publier l'arrêt correspondant.
        """
        ...

    async def request_stop(self) -> None:
        """Arrêt immédiat. Doit être appelé même si une motion est en cours."""
        ...

    async def camera_frame(self) -> bytes | None:
        """Dernière image de la caméra du robot, encodée en JPEG.

        `None` quand il n'y a pas de caméra (simulation) ou qu'elle n'a
        encore rien envoyé. Jamais une image inventée.
        """
        ...

    async def lidar_points(self) -> list[list[float]] | None:
        """Derniers points du lidar du robot, en mètres.

        `None` quand le lidar n'envoie rien. Jamais une carte inventée.
        """
        ...

    async def lidar_volume(self) -> dict[str, Any] | None:
        """Volume de voxels du lidar, pour une vue en 3D.

        `None` quand le lidar n'envoie rien. Jamais une carte inventée.
        """
        ...

    async def clearance_m(self, direction: str) -> float | None:
        """Distance libre dans une direction, en mètres.

        `direction` vaut `forward`, `backward`, `left` ou `right`, dans le
        repère du robot. `None` signifie « pas mesurée » (pas de lidar, carte
        ou pose périmée) : le service ne doit pas en déduire que la voie est
        libre, ni qu'elle est bloquée.
        """
        ...

    async def prepare_run(self) -> None:
        """Préparation avant le PREMIER ordre d'un programme.

        Le robot doit être sur ses quatre pattes pour se déplacer. Si sa
        posture est connue comme assise, l'adaptateur la relève explicitement
        avant le premier ordre, plutôt que de laisser le SDK le faire par
        effet de bord.

        Ne doit jamais lever : un refus de relèvement n'empêche pas
        d'exécuter le programme.
        """
        ...

    def supports(self, capability: Capability) -> bool:
        """Indique si une capacité est réellement disponible."""
        ...

    async def enter_standby(self) -> None:
        """Passe le robot en mode veille économique (coucher, coupure LiDAR)."""
        ...

    async def exit_standby(self) -> None:
        """Sort le robot du mode veille (rallume LiDAR, relève le robot)."""
        ...

    @property
    def lidar_active(self) -> bool:
        """Indique si le LiDAR physique est actuellement alimenté/actif."""
        return True

    async def set_lidar_switch(self, on: bool) -> None:
        """Active ou coupe le LiDAR physique du robot via rt/utlidar/switch."""
        pass

    async def enter_crouch_mode(self) -> None:
        """Active le mode accroupi (gait lent et stable type StaticWalk)."""
        pass

    async def exit_crouch_mode(self) -> None:
        """Désactive le mode accroupi et retourne progressivement à la posture normale."""
        pass

    @property
    def crouch_mode_active(self) -> bool:
        """Indique si le mode accroupi est actif."""
        return False

    async def enter_autonomous_mode(self) -> None:
        """Active le mode autonome (évitement d'obstacles et exploration)."""
        pass

    async def exit_autonomous_mode(self) -> None:
        """Désactive le mode autonome et immobilise le robot."""
        pass


@dataclass
class StopSignal:
    """Signal d'arrêt partagé et consultable.

    Volontairement simple et thread-safe : l'arrêt ne doit jamais dépendre
    d'une précisément synchronisation applicative.
    """

    _requested: bool = field(default=False, init=False, repr=False)
    reason: str | None = field(default=None, init=False, repr=False)

    def request(self, reason: str | None = None) -> None:
        if not self._requested:
            self._requested = True
            self.reason = reason

    @property
    def requested(self) -> bool:
        return self._requested

    def reset(self) -> None:
        self._requested = False
        self.reason = None