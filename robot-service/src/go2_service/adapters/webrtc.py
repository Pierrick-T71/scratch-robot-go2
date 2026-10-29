"""Adaptateur Unitree Go2 par le canal WebRTC de l'application mobile.

POURQUOI CET ADAPTATEUR EXISTE
------------------------------
Le Go2 de ce projet a ete mesure : son interface reseau (172.16.8.11, et
192.168.123.161 cote interne — c'est la meme machine) n'expose AUCUN
participant DDS. Sondes unicast sur les domaines 0 a 3, ports 7410 a 7480 :
aucune reponse. Le SDK officiel `unitree_sdk2py` ne peut donc pas le piloter
sur ce reseau, quel que soit le reglage d'interface.

En revanche, le robot expose le port 9991 : c'est le canal WebRTC, celui
qu'utilise l'application mobile. Le handshake y a ete verifie, puis un flux
d'etat reel a ete recu (239 messages en 12 s, ~20 Hz). C'est le seul chemin
de commande disponible, et il fonctionne en Wi-Fi.

SECURITE
--------
Meme contrat que l'adaptateur DDS, sans exception :

  * `physical_commands_enabled` vaut `False` sur la CLASSE. Un adaptateur
    fraichement construit refuse tout. L'ouverture passe par
    `enable_physical_commands()` sur l'INSTANCE, appelee par le service
    apres une demande explicite d'un adulte.
  * Toute instruction de mouvement revalide la vitesse contre
    `safety-limits.json` au dernier moment.
  * `Move` est une consigne PERSISTANTE : elle est rafraichie pendant le
    deplacement, et `request_stop()` envoie une consigne nulle puis
    `StopMove` SANS JAMAIS ATTENDRE DE REPONSE. Un arret ne doit pas
    dependre du reseau.
  * Le bilan de chaque instruction est construit sur l'ETAT MESURE. Sans
    mesure, le resultat est `timeout`, jamais `exact`.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import random
import time
from collections import deque
from typing import Any

from ..config import Limits
from ..obstacles import (
    free_distance_m,
    motion_direction,
    obstacle_cells,
    obstacle_message,
    obstacle_stop_message,
    required_clearance_m,
)
from ..recovery import AutoRecovery, RecoverySample
from ..state_safety import SafetySample, StateSafety
from ..validation import Capability, CommandKind, RobotCommand
from .base import (
    AdapterError,
    CommandOutcome,
    MotionPlan,
    Posture,
    RobotState,
    SafetyInterrupt,
    Status,
    StopSignal,
)
from .motion import (
    YAW_BANDE_MORTE_DEG,
    assert_speed_within_limits,
    plan_command,
    travelled_distance_cm,
    yaw_rate_for_remaining,
)
from .unitree import UNITREE_CAPABILITIES


log = logging.getLogger(__name__)


class WebRTCAdapter:
    """Pilote le Go2 par le canal de l'application mobile.

    Le canal est exclusif : si l'application mobile est ouverte sur le
    meme robot, la connexion est refusee (`RobotBusyError`).
    """

    name = "unitree-webrtc"

    #: Verrou de CLASSE, identique a l'adaptateur DDS.
    physical_commands_enabled = False

    #: Delai maximal pour recevoir le premier etat apres le handshake.
    #: C'est la SEULE preuve que le robot repond vraiment.
    STATE_HANDSHAKE_TIMEOUT_S = 6.0

    #: Periode de rafraichissement de la consigne `Move`. La commande
    #: persiste plusieurs secondes ; 5 Hz suffit et laisse le canal respirer
    #: (l'appel de commande attend une reponse, il ne peut pas suivre 200 Hz).
    MOVE_REFRESH_S = 0.2

    #: Periode de la boucle de mouvement, en secondes.
    #:
    #: 20 ms : la consigne de 1 s est arrêtée avec au plus 20 ms de retard,
    #: sans saturer le canal. C'est une horloge murale, pas un compteur de
    #: tours de boucle.
    MOVE_LOOP_S = 0.02

    #: Temps laissé à l'arrêt pour prendre effet avant de lire la distance.
    #: Le robot peut glisser quelques dixièmes de seconde après `StopMove`.
    STOP_SETTLE_S = 0.15

    #: Temps laissé au cap pour se stabiliser après une rotation. Plus long
    #: que pour une translation : c'est l'angle FINAL qui est annoncé.
    ROTATION_SETTLE_S = 0.25

    #: Delai maximal d'attente d'un acquittement de commande.
    COMMAND_TIMEOUT_S = 3.0

    #: Delai maximal d'attente de l'acquittement d'une COMMANDE DE POSTURE.
    #:
    #: Mesuré le 21/10/2026 : le robot acquitte « s'asseoir » après 2 s, mais
    #: parfois plus de 3 s (il attend la fin de son cycle de marche). Avec le
    #: delai court de 3 s, le service abandonnait la commande alors que le
    #: robot s'asseyait bel et bien : le programme se terminait, l'arret de
    #: fin de programme relevait le robot, et « s'asseoir » ne tenait pas.
    POSTURE_TIMEOUT_S = 8.0

    #: Duree maximale d'attente de la POSTURE PUBLIEE par le robot, quand
    #: son acquittement s'est perdu. Le robot s'assoit en 2 a 4 s.
    POSTURE_ATTENTE_S = 6.0

    #: Au-dela de ce silence, l'etat est declare perdu.
    STATE_STALE_S = 2.0

    #: Durée pendant laquelle une posture volontaire (assis, allongé, debout)
    #: est considérée en transition du point de vue de la détection de
    #: portage.
    POSTURE_GRACE_S = 5.0

    #: Période d'examen de la situation « le robot est tombé » (secondes).
    RELEVER_EXAMEN_S = 0.2

    #: Temps maximal d'attente du robot qui se relève, après `RecoveryStand`.
    RELEVER_ATTENTE_S = 12.0

    #: Pause avant une seconde tentative de relevé.
    RELEVER_REESSAI_S = 2.0

    #: Duree d'attente de la posture « allongé » après un `Damp` : le robot
    #: met 2 à 3 s à se poser.
    COUCHER_ATTENTE_S = 4.0

    #: Part de la fenêtre du lidar qui ne voit rien (pourcentage) à partir
    #: de laquelle on considère que le lidar est bloqué contre le sol.
    #:
    #: ⚠️ NON UTILISÉ : mesuré le 21/10/2026, ce pourcentage passe de 0-8 %
    #: (debout) à 61-70 % (allongé) alors que le lidar tourne librement.
    #: Ce n'est donc pas un indice de blocage.
    LIDAR_SALISSURE_SEUIL = 30.0

    #: Fraction de la rotation de référence en dessous (ou au-dessus) de
    #: laquelle on considère que le lidar est bloqué : sa fenêtre frotte
    #: contre le sol et son contrôleur change de régime.
    #:
    #: Mesuré le 21/10/2026, avec une médiane de 0,0203 :
    #:
    #: | Situation | ratio | écart |
    #: |---|---|---|
    #: | normal | 0,0202 – 0,0203 | ±1 % |
    #: | relèvement | 0,0182 | −10 % |
    #: | **bloqué (14:14)** | **0,0334** | **+64 %** |
    #: | **bloqué (13:55)** | **0,0114** | **−44 %** |
    #:
    #: Le seuil de 25 % sépare les deux.
    LIDAR_ROTATION_BLOQUEE = 0.75

    #: Nombre de mesures de rotation Gardées pour calculer la médiane.
    LIDAR_ROTATIONS_MAX = 60

    #: Nombre de mesures minimum avant de pouvoir conclure.
    LIDAR_ROTATIONS_MIN = 10

    #: Au-delà de cette ancienneté, l'état du lidar est considéré comme
    #: périmé : on ne conclut pas à partir d'une mesure morte.
    LIDAR_ETAT_PERIME_S = 3.0

    #: Variation de hauteur (m) sous laquelle le robot est considere immobile.
    STABLE_HEIGHT_M = 0.003

    #: Periode d'echantillonnage de la hauteur, en secondes.
    STABLE_SAMPLE_S = 0.2

    #: Nombre d'echantillons consecutifs stables pour valider l'immobilite.
    STABLE_SAMPLES = 5

    #: Attente maximale de la stabilisation (transition de posture).
    STABLE_TIMEOUT_S = 6.0

    #: En dessous de cette fraction de la hauteur debout, le robot est assis.
    #: Un Go2 debout fait ~0,32 m, assis ~0,22 m.
    SITUE_RATIO = 0.85

    #: En dessous de cette fraction de la hauteur debout, le robot est
    #: allongé par terre. Mesuré : debout ~0,32 m, assis ~0,22 m,
    #: allongé ~0,06 m.
    COCHE_RATIO = 0.5

    #: Codes d'etat signales « le robot est debout et pret ».
    #:
    #: Mesure sur la machine : `1013` = debout et immobile, `100` = en
    #: mouvement. Les DEUX sont des états où le robot est prêt à partir.
    ETAT_PRET = frozenset({1013, 100})

    #: Code d'etat : le robot est ASSIS.
    ETAT_ASSIS_CODE = 1007

    #: Code d'etat : le robot est ALLOUGE par terre (apres un `Damp`).
    ETAT_ALLOUGE_CODE = 1001

    #: Code d'etat publie pendant une TRANSITION de posture. Le robot
    #: ignore alors les consignes de mouvement — et les lui envoyer
    #: l'empeche meme de finir sa transition.
    ETAT_TRANSITION = 1002

    #: Code d'etat publie au DEBUT d'une transition vers la position
    #: assise ou allongee (`1006`). Pendant cette transition, le robot est
    #: en train de se poser : lui envoyer `Move` le releverait.
    ETAT_TRANSITION_ASSIS = 1006

    #: Code d'etat publie quand le robot est ASSIS.
    ETAT_ASSIS = 1007

    #: Attente maximale du retour a l'etat "pret".
    PRET_TIMEOUT_S = 12.0

    #: Periode minimum entre deux images encodees (secondes).
    #: 5 images par seconde suffisent a une vue d'enfant, et cela evite
    #: de saturer le processeur du service.
    CAMERA_PERIODE_S = 0.2

    #: Duree pendant laquelle la camera reste active apres la derniere
    #: requete. Le flux MJPEG est ouvert par l'interface ; quand elle le
    #: ferme, on cesse d'encoder pour ne pas bruler le processeur.
    CAMERA_ACTIVE_S = 5.0

    #: Periode de traitement des cartes du lidar (secondes).
    #:
    #: Le lidar publie plusieurs cartes par seconde. Les convertir a chaque
    #: message monopolisait le processeur et retardait les requetes HTTP du
    #: mode manuel de plusieurs centaines de millisecondes. Deux cartes par
    #: seconde suffisent pour la vue et pour le controle d'obstacle.
    LIDAR_TRAITEMENT_S = 0.5
    #: Délai d'inactivité au-delà duquel le LiDAR est coupé pour économiser la batterie.
    LIDAR_INACTIF_TIMEOUT_S = 15.0

    #: Au-dela de cette anciennete, la carte du lidar est consideree
    #: comme perimee : mieux vaut une vue vide qu'une carte trompeuse.
    LIDAR_PERIME_S = 2.0

    #: Periode du controle d'obstacle pendant un deplacement, en secondes.
    #:
    #: 10 Hz : a 0,30 m/s, le chien avance de 3 cm entre deux mesures. La
    #: marge de `BODY_CLEARANCE_M` couvre largement ce delai.
    OBSTACLE_CHECK_S = 0.1

    def __init__(
        self,
        limits: Limits,
        robot_ip: str,
        aes_key: str | None = None,
    ) -> None:
        self._limits = limits
        self._robot_ip = robot_ip
        self._aes_key = aes_key
        self.physical_commands_enabled = False
        #: Sécurité lidar du service : quand elle est active, `clearance_m`
        #: mesure la place libre et l'exécution refuse un pas qui ne tient pas.
        #: Désactivée par un adulte, elle renvoie `None` (aucune mesure) : le
        #: service ne bloque plus, mais l'anti-obstacle interne du Go2 reste
        #: actif et peut toujours arrêter le robot.
        self._obstacle_safety_enabled = True

        self._connexion: Any = None
        self._rtc: Any = None
        self._sport_cmd: Any = None
        self._types_canal: Any = None

        self._connected = False
        self._state = RobotState.UNKNOWN
        self._posture: Posture | None = None

        self._position: tuple[float, float, float] | None = None
        self._yaw: float | None = None
        #: Efforts mesurés sous les quatre pieds (`rt/lf/lowstate`).
        #: La somme sous 60 signifie qu'aucun pied ne porte (voir
        #: `state_safety.py`).
        self._foot_force: tuple[int, ...] | None = None
        self._foot_force_at: float | None = None
        self._pieds_deja_logges = False
        #: Décision de portage, avec verrouillage.
        self._securite = StateSafety()
        #: Fin d'une fenêtre pendant laquelle un changement de posture
        #: volontaire (s'asseoir, se coucher, se relever) ne doit pas être pris
        #: pour un portage : les pieds se déchargent avant que le code d'état
        #: ait basculé sur « assis », « allongé » ou « debout ».
        self._posture_grace_until = 0.0
        #: Cap CUMULÉ (déroulé) depuis la connexion, en radians.
        #:
        #: `imu_state.rpy[2]` revient de -π à +π : une rotation qui franchit
        #: cette limite ferait un saut de 358° si on lisait le cap brut. On
        #: additionne donc les écarts successifs les plus courts, ce qui donne
        #: un cap continu, seul utilisable pour asservir une rotation.
        self._cap_cumule: float | None = None
        self._yaw_precedent: float | None = None
        #: Horodatage (monotonic) du dernier cap REÇU. Sert à refuser une
        #: rotation quand la mesure n'arrive plus.
        self._cap_mesure_at: float | None = None
        self._battery: float | None = None
        self._temperature_ntc1: int | None = None
        self._motor_temp_max: int | None = None
        self._velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._mode: int | None = None
        self._last_state_at: float | None = None
        #: Code d'etat publie par le robot (100 = pret, 1002 = transition).
        self._code_etat: int | None = None
        #: Code d'état précédent : permet de journaliser les changements
        #: (`1013` debout, `100` en mouvement, `1007` assis, `1001` allongé).
        self._code_etat_precedent: int | None = None
        #: Plus haute hauteur vue depuis la connexion : sert de reference
        #: pour savoir si le robot est actuellement assis.
        self._hauteur_max: float | None = None
        #: Derniere image de la camera du robot, en JPEG.
        self._dernier_jpeg: bytes | None = None
        self._dernier_jpeg_at: float = 0.0
        self._tache_video: asyncio.Task[None] | None = None
        #: Derniere demande de l'interface pour la camera.
        self._camera_demande_at: float = 0.0
        #: Le canal video a-t-il deja ete ouvert ?
        self._video_demarre = False
        #: Derniere carte du lidar recue.
        self._points_lidar: list[list[float]] | None = None
        self._points_lidar_at: float = 0.0
        #: Derniere conversion complete d'une carte du lidar.
        self._lidar_traite_at: float = 0.0
        self._lidar_vus: set[str] = set()
        self._lidar_raison: str | None = None
        self._lidar_compte_at: float | None = None
        #: Dernier volume de voxels recu, pour la vue en 3D.
        self._volume_lidar: dict[str, Any] | None = None
        self._volume_lidar_at: float = 0.0
        self._lidar_origine_at: float | None = None
        self._pose_vue = False
        #: Pose du robot dans la carte du lidar : position et cap.
        self._pose_robot: dict[str, float] | None = None
        #: Horodatage (monotonic) de la dernière pose reçue.
        self._pose_robot_at: float = 0.0
        #: Cases d'obstacles du lidar, SANS le sol, vues du dessus.
        self._obstacles_lidar: list[tuple[float, float]] | None = None
        self._obstacles_lidar_at: float = 0.0
        #: Roulis de l'IMU, en radians. Sert au relevage automatique : un
        #: chien couché sur le flanc a un roulis de l'ordre de 90°.
        self._roullis: float | None = None
        #: Avons-nous demandé nous-mêmes l'allongement du robot ? (bloc
        #: « se coucher » ou arrêt de sécurité). Tant que c'est vrai, on ne
        #: le relève pas tout seul : c'est nous qui l'avions allongé.
        self._allonge_demande = False
        #: État d'alimentation du LiDAR physique sur rt/utlidar/switch.
        self._lidar_physique_actif = True
        #: Horodatage du dernier besoin effectif du LiDAR.
        self._derniere_requete_lidar: float = time.monotonic()
        #: Un programme est-il en cours ? Pendant un programme, c'est lui
        #: qui prépare le robot (`prepare_run` le relève).
        self._programme_en_cours = False
        #: Mode veille actif (robot couché, LiDAR coupé pour économie de batterie).
        self._en_veille = False
        #: Mode autonome actif (exploration et évitement d'obstacles en continu).
        self._en_autonome = False
        #: Mode accroupi actif (StaticWalk / démarche rampante lente et contrôlée).
        self._crouch_mode = False
        #: Décision de relevage automatique (module `recovery.py`).
        self._relever_auto = AutoRecovery()
        #: Tâche de relevage en cours, et dernier examen de la situation.
        self._tache_relever: asyncio.Task[None] | None = None
        self._relever_examen_at: float = 0.0
        #: Raison du dernier relevage automatique, affichée dans l'état.
        self._recovery_reason: str | None = None
        #: Dernier état du lidar (`rt/utlidar/lidar_state`) : rotation,
        #: salissure, erreur.
        self._etat_lidar: dict[str, Any] | None = None
        #: Signature de cet état, pour ne journaliser que les changements.
        self._signature_lidar: tuple[Any, ...] | None = None
        #: Quand cet état a été reçu (monotonic).
        self._etat_lidar_at: float = 0.0
        #: Dernières rotations mesurées : la médiane donne la rotation
        #: typique du lidar, insensible aux pics.
        self._rotations: deque[float] = deque(maxlen=self.LIDAR_ROTATIONS_MAX)

        self._premier_etat: asyncio.Event | None = None

    # -- Informations d'identification -------------------------------------

    @property
    def robot_ip(self) -> str:
        return self._robot_ip

    @property
    def network_interface(self) -> str:
        """Sans objet ici : le canal passe par IP, pas par interface."""
        return "webrtc"

    @property
    def last_error(self) -> str | None:
        return None

    @property
    def safety_stop_reason(self) -> str | None:
        """Raison du verrouillage de sécurité en cours, sinon `None`.

        Propriété volontairement synchrone : le chien de garde la lit dans sa
        boucle, sans attendre le réseau.
        """
        return self._securite.reason if self._securite.latched else None

    def enable_physical_commands(self) -> None:
        """Ouvre le pilotage pour CETTE instance, jamais pour la classe."""
        self.physical_commands_enabled = True

    def supports(self, capability: Capability) -> bool:
        return capability in UNITREE_CAPABILITIES

    # -- Cycle de vie ------------------------------------------------------

    async def connect(self) -> None:
        """Ouvre le canal WebRTC et attend un PREMIER ETAT REEL."""
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé sur cette instance : "
                "aucune commande ne sera envoyée.",
            )

        if not self._aes_key:
            raise AdapterError(
                "La clé AES-128 du robot est absente. Le firmware récent "
                "l’exige pour ouvrir le canal (voir docs/ROBOT_SETUP.md).",
            )

        try:
            from unitree_webrtc_connect import (  # type: ignore[import-not-found]
                DATA_CHANNEL_TYPE,
                RTC_TOPIC,
                SPORT_CMD,
                UnitreeWebRTCConnection,
                WebRTCConnectionMethod,
            )
        except ImportError as exc:
            raise AdapterError(
                "La bibliothèque « unitree_webrtc_connect » n’est pas "
                "installée sur cette machine (voir docs/ROBOT_SETUP.md).",
            ) from exc

        self._rtc = RTC_TOPIC
        self._sport_cmd = dict(SPORT_CMD)
        self._sport_cmd.update({
            "StaticWalk": 1061,
            "ClassicWalk": 1044,
            "FreeAvoid": 2048,
        })
        self._types_canal = DATA_CHANNEL_TYPE
        self._premier_etat = asyncio.Event()
        # Le cap cumulé repart de zéro à chaque connexion : une valeur gardée
        # d'une session précédente ne décrit plus le robot.
        self._cap_cumule = None
        self._yaw_precedent = None
        self._cap_mesure_at = None
        # Une nouvelle liaison repart d'une surveillance neuve : un
        # verrouillage de l'ancienne session ne doit pas bloquer le robot.
        self._securite.reset()
        self._foot_force = None
        self._foot_force_at = None
        self._pieds_deja_logges = False
        self._posture_grace_until = 0.0
        self._code_etat_precedent = None

        try:
            self._connexion = UnitreeWebRTCConnection(
                WebRTCConnectionMethod.LocalSTA,
                ip=self._robot_ip,
                aes_128_key=self._aes_key,
            )
            await self._connexion.connect()
        except Exception as exc:  # noqa: BLE001 - le SDK levere des types varies
            self._connexion = None
            raise AdapterError(
                f"Connexion WebRTC au robot {self._robot_ip} impossible "
                f"({type(exc).__name__} : {exc}).",
                recoverable=True,
            ) from exc

        # ⚠️ Le handshake seul ne prouve rien : il peut reussir alors que le
        # robot ne publie aucun etat. On attend donc un message REEL.
        try:
            self._connexion.datachannel.pub_sub.subscribe(
                RTC_TOPIC["LF_SPORT_MOD_STATE"], self._sur_etat
            )
            self._connexion.datachannel.pub_sub.subscribe(
                RTC_TOPIC["LOW_STATE"], self._sur_batterie
            )
        except Exception as exc:  # noqa: BLE001
            await self.disconnect()
            raise AdapterError(
                f"Abonnement à l’état du robot impossible ({exc}).",
                recoverable=True,
            ) from exc

        try:
            await asyncio.wait_for(
                self._premier_etat.wait(), timeout=self.STATE_HANDSHAKE_TIMEOUT_S
            )
        except asyncio.TimeoutError as exc:
            await self.disconnect()
            raise AdapterError(
                f"Aucun état reçu du robot après {self.STATE_HANDSHAKE_TIMEOUT_S:g} s : "
                "le canal est ouvert mais le robot ne répond pas.",
                recoverable=True,
            ) from exc

        self._connected = True
        self._state = RobotState.IDLE

        # La camera n'est ouverte QUE si l'interface la demande : la decoder
        # en permanence monopolisait un coeur pour rien et retardait le
        # pilotage manuel. Le lidar, lui, reste utile au contrôle d'obstacle
        # des programmes.
        await self._demarrer_lidar()

    async def disconnect(self) -> None:
        """Immobilise le robot, puis ferme le canal."""
        try:
            await self.request_stop()
        except Exception:  # noqa: BLE001 - on veut fermer quand meme
            pass

        if self._tache_video is not None:
            self._tache_video.cancel()
            self._tache_video = None
        self._dernier_jpeg = None
        self._dernier_jpeg_at = 0.0
        self._camera_demande_at = 0.0
        self._video_demarre = False

        connexion = self._connexion
        if connexion is not None:
            try:
                connexion.datachannel.switchAudioChannel(False)
            except Exception:  # noqa: BLE001
                pass
            try:
                connexion.video.switchVideoChannel(False)
            except Exception:  # noqa: BLE001
                pass
            try:
                await connexion.disconnect()
            except Exception:  # noqa: BLE001
                # Repli : fermer la connexion pair-a-pair directement.
                try:
                    await connexion.pc.close()
                except Exception:  # noqa: BLE001
                    pass

        self._connexion = None
        self._connected = False
        self._last_state_at = None
        self._code_etat_precedent = None
        self._cap_cumule = None
        self._yaw_precedent = None
        self._cap_mesure_at = None
        self._state = RobotState.DISCONNECTED

    # -- Reception de l'etat ----------------------------------------------

    def _sur_etat(self, message: Any) -> None:
        """Memorise l'etat publie par le robot. Ne doit jamais lever."""
        donnees = (message or {}).get("data") or {}
        maintenant = time.monotonic()
        try:
            # L'etat du robot est lu EN PREMIER : la hauteur de reference
            # doit etre jugee avec le code du MEME message.
            code_etat = donnees.get("error_code")
            if isinstance(code_etat, (int, float)):
                nouveau_code = int(code_etat)
                if nouveau_code != self._code_etat_precedent:
                    # Le code d'état dit ce que le robot fait vraiment
                    # (`100` en mouvement, `1013` debout immobile, `1007`
                    # assis, `1001` allongé). Le journaliser permet de
                    # relire une sequence apres coup.
                    log.info("Etat du robot : %s", nouveau_code)
                    self._code_etat_precedent = nouveau_code
                self._code_etat = nouveau_code

            position = donnees.get("position") or []
            if len(position) >= 3:
                self._position = (
                    float(position[0]),
                    float(position[1]),
                    float(position[2]),
                )
                # Reference de la hauteur debout : on ne retient QUE les
                # hauteurs vues quand le robot dit qu'il est debout. Pendant
                # un mouvement violent, l'odometrie s'emballe (0,52 m pendant
                # un bond, pour un robot de 0,32 m) : retenir cette valeur
                # ferait croire ensuite que le robot ne peut pas etre debout.
                if self._code_etat is None or self._code_etat in self.ETAT_PRET:
                    hauteur = float(position[2])
                    if self._hauteur_max is None or hauteur > self._hauteur_max:
                        self._hauteur_max = hauteur

            imu = donnees.get("imu_state") or {}
            rpy = imu.get("rpy") or []
            if len(rpy) >= 3:
                # Le roulis ne sert PAS à arrêter le robot (une transition de
                # posture le fait mentir). Il sert au relevage automatique :
                # un chien couché sur le flanc a un roulis de 90°.
                self._roullis = float(rpy[0])
                yaw = float(rpy[2])
                if self._yaw_precedent is None or self._cap_cumule is None:
                    self._cap_cumule = yaw
                else:
                    # Écart le plus court entre deux caps : c'est lui qui
                    # « déroule » le passage de +π à -π.
                    delta = (
                        (yaw - self._yaw_precedent + math.pi)
                        % (2.0 * math.pi)
                        - math.pi
                    )
                    self._cap_cumule += delta
                self._yaw_precedent = yaw
                self._yaw = yaw
                self._cap_mesure_at = maintenant

            vitesse = donnees.get("velocity") or []
            if len(vitesse) >= 3:
                self._velocity = (
                    float(vitesse[0]),
                    float(vitesse[1]),
                    float(vitesse[2]),
                )

            mode = donnees.get("mode")
            if isinstance(mode, (int, float)):
                self._mode = int(mode)

            self._last_state_at = maintenant
        except (TypeError, ValueError, AttributeError):
            # Un etat illisible vaut « inconnu », jamais une valeur inventee.
            pass

        self._evaluer_securite(maintenant)
        self._examiner_relever(maintenant)
        self._gerer_inactivite_lidar(maintenant)

        if self._premier_etat is not None:
            self._premier_etat.set()

    def _sur_batterie(self, message: Any) -> None:
        """Lit le niveau de batterie et les efforts dans les pieds.

        Le topic `rt/lf/lowstate` porte les deux. Les efforts sont la SEULE
        mesure directe du contact avec le sol : c'est eux qui permettent de
        détecter un robot soulevé.
        """
        donnees = (message or {}).get("data") or {}
        maintenant = time.monotonic()

        candidats: list[Any] = []
        bms = donnees.get("bms_state")
        if isinstance(bms, dict):
            candidats.append(bms.get("soc"))
        candidats.append(donnees.get("soc"))
        for valeur in candidats:
            if isinstance(valeur, (int, float)):
                self._battery = float(valeur)
                break

        pieds = donnees.get("foot_force")
        if isinstance(pieds, (list, tuple)) and len(pieds) == 4:
            try:
                forces = tuple(int(float(valeur)) for valeur in pieds)
            except (TypeError, ValueError):
                forces = None
            if forces is not None:
                self._foot_force = forces
                self._foot_force_at = maintenant
                if not self._pieds_deja_logges:
                    self._pieds_deja_logges = True
                    log.info("Efforts aux pieds mesures : %s", list(forces))

        temp_ntc1 = donnees.get("temperature_ntc1")
        if isinstance(temp_ntc1, (int, float)):
            self._temperature_ntc1 = int(temp_ntc1)

        moteurs = donnees.get("motor_state")
        if isinstance(moteurs, list):
            temps = [
                m.get("temperature")
                for m in moteurs
                if isinstance(m, dict) and isinstance(m.get("temperature"), (int, float))
            ]
            if temps:
                self._motor_temp_max = int(max(temps))

        self._evaluer_securite(maintenant)

    # -- Surveillance des appuis --------------------------------------------

    @property
    def temperature_ntc1(self) -> int | None:
        """Température interne de la carte mère/châssis en °C."""
        return self._temperature_ntc1

    @property
    def motor_temp_max(self) -> int | None:
        """Température maximale relevée parmi les moteurs en °C."""
        return self._motor_temp_max

    @property
    def lidar_active(self) -> bool:
        """Indique si le LiDAR physique est actuellement alimenté/actif."""
        return self._lidar_physique_actif

    @property
    def obstacle_safety_enabled(self) -> bool:
        """Sécurité lidar du service : quand elle est active, clearance_m mesure la place libre."""
        return self._obstacle_safety_enabled

    @obstacle_safety_enabled.setter
    def obstacle_safety_enabled(self, value: bool) -> None:
        active = bool(value)
        self._obstacle_safety_enabled = active
        if active and self._connected and not self._lidar_physique_actif and not self._en_veille:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.set_lidar_switch(True))
            except RuntimeError:
                pass

    async def set_lidar_switch(self, on: bool) -> None:
        """Active ou coupe le LiDAR physique du Go2 via rt/utlidar/switch."""
        connexion = self._connexion
        if connexion is None or not self._connected:
            return
        if self._lidar_physique_actif == on:
            return
        t_switch = self._rtc.get("ULIDAR_SWITCH", "rt/utlidar/switch")
        valeur = "ON" if on else "OFF"
        try:
            canal = connexion.datachannel.pub_sub
            canal.publish_without_callback(t_switch, valeur)
            canal.publish_without_callback(t_switch, "on" if on else "off")
            self._lidar_physique_actif = on
            if on:
                self._derniere_requete_lidar = time.monotonic()
            log.info(
                "LiDAR physique %s (topic %s, data: %r).",
                "allumé" if on else "coupé",
                t_switch,
                valeur,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Impossible de changer l'état du LiDAR (%s) : %s", valeur, exc)

    def _gerer_inactivite_lidar(self, maintenant: float) -> None:
        """Coupe automatiquement le LiDAR en cas d'inactivité pour économiser la batterie."""
        if not self._connected or self._connexion is None or self._en_veille:
            return
        if not self._lidar_physique_actif:
            return
        if self._programme_en_cours:
            return
        # Mode sécurité actif : interdiction stricte de couper le LiDAR par inactivité
        if self._obstacle_safety_enabled:
            return
        if maintenant - self._derniere_requete_lidar < self.LIDAR_INACTIF_TIMEOUT_S:
            return
        t_switch = self._rtc.get("ULIDAR_SWITCH", "rt/utlidar/switch")
        try:
            self._connexion.datachannel.pub_sub.publish_without_callback(t_switch, "off")
            self._lidar_physique_actif = False
            log.info(
                "Inactivité (> %.0f s) : coupure automatique du LiDAR physique pour économiser la batterie.",
                self.LIDAR_INACTIF_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Échec de la coupure automatique du LiDAR : %s", exc)

    def _evaluer_securite(self, maintenant: float) -> None:
        """Met à jour le verrouillage de sécurité, sans jamais lever."""
        if self._last_state_at is None or self._code_etat is None:
            # Sans état du robot, on ne sait pas s'il est assis, debout ou
            # allongé : toute conclusion serait une supposition.
            return

        # Une posture volontaire vient d'être demandée : les efforts peuvent
        # disparaître avant que le code d'état ne passe à « assis »,
        # « allongé » ou « debout ». On laisse la transition se terminer.
        if not self._securite.latched and maintenant < self._posture_grace_until:
            return

        try:
            au_sol = self._est_assis() or self._est_alleonge()
            evenement = self._securite.update(
                SafetySample(
                    now=maintenant,
                    au_sol=au_sol,
                    foot_force=self._foot_force,
                    foot_force_at=self._foot_force_at,
                )
            )
        except Exception:  # noqa: BLE001 - un callback ne doit jamais lever
            log.exception("Surveillance de sécurité : mesure illisible.")
            return

        if evenement.tripped:
            self._declencher_arret_securite(
                evenement.reason or "Le robot s’est arrêté pour sa sécurité."
            )
        elif evenement.cleared:
            log.info(
                "Sécurité : appuis revenus normaux, robot réarmé."
            )
            if self._state is RobotState.ERROR:
                self._state = RobotState.IDLE

    # -- Relevage automatique -----------------------------------------------

    def _examiner_relever(self, maintenant: float) -> None:
        """Regarde si le robot tombé doit se relever tout seul.

        On n'examine pas à chaque message : une fois toutes les 200 ms.
        Le robot est relevé quand il est **sur le flanc** (son lidar, devant
        la tête, balaie alors un plan vertical et frotte le sol), et que
        personne ne l'a allongé.
        """
        if maintenant - self._relever_examen_at < self.RELEVER_EXAMEN_S:
            return
        self._relever_examen_at = maintenant

        tache = self._tache_relever
        if tache is not None and not tache.done():
            return
        if self._securite.latched or self._en_veille:
            # Le robot est porte, ou en veille volontaire :
            # on ne fait aucune manoeuvre physique.
            return

        try:
            evenement = self._relever_auto.update(
                RecoverySample(
                    now=maintenant,
                    allongé=self._est_alleonge(),
                    lidar_bloque=self._lidar_bloque(),
                    demande_par_nous=self._allonge_demande,
                    programme_en_cours=self._programme_en_cours,
                )
            )
        except Exception:  # noqa: BLE001 - un callback ne doit jamais lever
            log.exception("Relevage automatique : mesure illisible.")
            return

        if not evenement.triggered:
            return

        self._recovery_reason = evenement.reason
        log.warning(
            "Relevage automatique : %s", evenement.reason or "le robot est tombé."
        )
        try:
            boucle = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._tache_relever = boucle.create_task(self._relever_automatiquement())

    async def _relever_automatiquement(self) -> None:
        """Relève le robot allongé, pour qu'il ne frotte pas sur son lidar.

        On utilise `StandUp`, la même commande que la préparation d'un
        programme : elle a été vérifiée depuis la position allongée.
        """
        if self._en_veille:
            return
        for essai in range(2):
            if self._securite.latched:
                return
            try:
                await self._appliquer_posture("StandUp", Posture.STAND)
            except SafetyInterrupt:
                return
            except AdapterError as exc:
                log.warning("Relevage automatique : commande refusée (%s).", exc)
            if await self._attendre_debout(self.RELEVER_ATTENTE_S):
                log.info("Relevage automatique : le robot est debout.")
                self._allonge_demande = False
                self._recovery_reason = "Le robot s’est relevé tout seul."
                return
            await asyncio.sleep(self.RELEVER_REESSAI_S)

        self._recovery_reason = (
            "Le robot est allongé et n’a pas pu se relever tout seul : "
            "demande à un adulte de le redresser."
        )
        log.warning("Relevage automatique : le robot n'a pas pu se relever.")

    def _lidar_bloque(self) -> bool | None:
        """Le lidar frotte-t-il le sol ?

        Le lidar publie sa rotation **réelle** (`com_rotation_speed`) et la
        rotation **demandée** (`sys_rotation_speed`). Quand sa fenêtre
        tournante frotte contre le sol, le contrôleur du lidar change de
        régime : sa rotation **s'écarte** de la valeur normale.

        On compare donc la rotation réelle à la **médiane** des rotations
        récentes : c'est la valeur typique du lidar, et elle ne bouge pas
        quand une mesure est anormale.

        Mesuré le 21/10/2026 sur le robot réel (ratio = rotation réelle /
        rotation demandée, médiane = 0,0203) :

        | Situation | ratio | écart à la médiane |
        |---|---|---|
        | normal, debout ou allongé | 0,0202 – 0,0203 | ±1 % |
        | pendant un relèvement | 0,0182 | −10 % |
        | **lidar bloqué** (14:14:44) | **0,0334** | **+64 %** |
        | **lidar bloqué** (13:55:59) | **0,0114** | **−44 %** |

        Le blocage se manifeste donc **dans les deux sens** : c'est l'écart à
        la médiane qui compte, pas seulement une baisse. Le seuil est donc
        de **25 %** dans les deux sens.

        `None` tant qu'on n'a pas assez de mesures : on ne conclut jamais
        dans le vide.

        ⚠️ Le `dirty_percentage` du lidar NE veut PAS dire « bloqué » :
        mesuré le 21/10/2026, il passe de 0-8 % (debout) à 61-70 % (allongé)
        alors que le lidar tourne librement. Ce n'est donc pas notre
        critère.
        """
        etat = self._etat_lidar
        if etat is None:
            return None
        if time.monotonic() - self._etat_lidar_at > self.LIDAR_ETAT_PERIME_S:
            return None

        erreur = etat.get("erreur")
        if isinstance(erreur, (int, float)) and erreur != 0:
            # Le firmware signale lui-même que le lidar a un problème.
            return True

        ratio = etat.get("ratio")
        if not isinstance(ratio, (int, float)):
            return None
        nominale = self._rotation_mediane()
        if nominale is None:
            return None
        ecart = ratio / nominale
        return (
            ecart < self.LIDAR_ROTATION_BLOQUEE
            or ecart > 1.0 / self.LIDAR_ROTATION_BLOQUEE
        )

    def _rotation_mediane(self) -> float | None:
        """Rotation typique du lidar : la médiane des dernières mesures.

        La médiane, et non le maximum : un pic de mesure (on a vu 0,0729
        pendant une pose, contre 0,0203 en temps normal) ne doit pas
        déplacer l'échelle. Un maximum l'aurait déplacée de 3,6 fois, et
        tout aurait ensuite semblé « bloqué ».

        Seules les mesures **normales** entrent dans l'historique : un
        blocage durable ne doit pas décaler la référence, sinon le
        détecteur s'éteindrait de lui-même au bout de quelques secondes.
        """
        if len(self._rotations) < self.LIDAR_ROTATIONS_MIN:
            return None
        triees = sorted(self._rotations)
        milieu = len(triees) // 2
        if len(triees) % 2:
            return triees[milieu]
        return (triees[milieu - 1] + triees[milieu]) / 2.0

    def _rotation_normale(self, ratio: float) -> bool:
        """Cette rotation est-elle dans le régime normal du lidar ?"""
        nominale = self._rotation_mediane()
        if nominale is None:
            # On n'a pas encore de référence : on accepte la mesure.
            return True
        ecart = ratio / nominale
        return (
            self.LIDAR_ROTATION_BLOQUEE
            <= ecart
            <= 1.0 / self.LIDAR_ROTATION_BLOQUEE
        )

    async def _attendre_debout(self, timeout_s: float) -> bool:
        """Attend que le robot soit debout (code d'état `100` ou `1013`)."""
        fin = time.monotonic() + timeout_s
        while time.monotonic() < fin:
            if self._est_debout():
                return True
            await asyncio.sleep(0.2)
        return self._est_debout()

    def _declencher_arret_securite(self, raison: str) -> None:
        """Arrête la marche et relâche les pattes du robot porté.

        On annule d'abord la consigne de vitesse persistante, puis on envoie
        `Damp`. C'est le seul ordre SDK qui coupe l'équilibrage actif : sans
        lui, le robot continue à bouger les pattes pour retrouver son assiette
        dans les mains de la personne qui le porte.

        `Damp` rend le robot mou. C'est voulu ici : il est soulevé, donc
        soutenu. On ne l'utilise jamais pour un robot simplement posé au sol.
        """
        self._state = RobotState.ERROR
        log.warning(
            "ARRET DE SECURITE : %s (pieds=%s, etat=%s)",
            raison,
            list(self._foot_force) if self._foot_force else None,
            self._code_etat,
        )

        if self._connexion is None:
            return

        if not (self._est_assis() or self._est_alleonge()):
            try:
                self._envoyer_move(0.0, 0.0, 0.0)
                self._envoyer_sans_reponse("StopMove")
            except Exception:  # noqa: BLE001 - l'arrêt doit être tenté quand même
                log.exception("Sécurité : l’arrêt de vitesse n’a pas pu être envoyé.")
            try:
                # Coupe l'équilibrage actif : les pattes cessent de chercher
                # un appui. Le robot reste soutenu par la personne.
                self._envoyer_sans_reponse("Damp")
                self._allonge_demande = True
            except Exception:  # noqa: BLE001
                log.exception("Sécurité : le relâchement des pattes a échoué.")

    # -- Etat --------------------------------------------------------------

    async def get_status(self) -> Status:
        """Etat connu. Ne leve jamais."""
        if not self._connected:
            return Status(
                connected=False,
                state=RobotState.DISCONNECTED,
                capabilities=UNITREE_CAPABILITIES,
                blocked_reason="Le service n’est pas connecté au robot.",
                safety_reason=self.safety_stop_reason,
            )

        bloque: str | None = None
        if (
            self._last_state_at is None
            or time.monotonic() - self._last_state_at > self.STATE_STALE_S
        ):
            bloque = "Le robot n’envoie plus son état."

        return Status(
            connected=True,
            state=RobotState.ERROR if bloque else self._state,
            capabilities=UNITREE_CAPABILITIES,
            blocked_reason=bloque,
            position_m=self._position,
            yaw_rad=self._yaw,
            battery_percent=self._battery,
            posture=self._posture,
            safety_reason=self.safety_stop_reason,
            recovery_reason=self._recovery_reason,
        )

    # -- Emission ----------------------------------------------------------

    def _enveloppe(self, nom: str | int, parametre: Any = "") -> dict[str, Any]:
        """Construit le message attendu par le canal, sans attendre de reponse."""
        identifiant = int(time.time() * 1000) % 2147483648 + random.randint(0, 1000)
        api_id = nom if isinstance(nom, int) else (self._sport_cmd or {}).get(nom)
        if api_id is None:
            raise KeyError(nom)
        return {
            "header": {
                "identity": {"id": identifiant, "api_id": api_id}
            },
            "parameter": parametre
            if isinstance(parametre, str)
            else json.dumps(parametre),
        }

    def _envoyer_sans_reponse(self, nom: str, parametre: Any = "") -> None:
        """Envoi immediat, sans attente. Utilise pour Move et StopMove.

        L'arret ne doit JAMAIS dependre d'une reponse : si le robot ne
        repond pas, il faut quand meme que la consigne nulle parte.
        """
        connexion = self._connexion
        if connexion is None:
            return
        if nom != "Move":
            # Journal des ordres de posture et d'arret : c'est ce qui permet
            # de relire, apres coup, ce que le robot a recu.
            log.info("Commande envoyee au robot : %s", nom)
        connexion.datachannel.pub_sub.publish_without_callback(
            topic=self._rtc["SPORT_MOD"],
            data=self._enveloppe(nom, parametre),
            msg_type=self._types_canal["REQUEST"],
        )

    def _envoyer_move(self, vx: float, vy: float, vyaw: float) -> None:
        self._envoyer_sans_reponse("Move", {"x": vx, "y": vy, "z": vyaw})

    async def _commander(
        self,
        nom: str,
        parametre: Any = "",
        timeout_s: float | None = None,
    ) -> int | None:
        """Envoie une commande et attend son acquittement.

        Retourne le code de statut renvoye par le robot, ou `None` si le
        robot n'a pas repondu dans le delai.

        `timeout_s` : les postures ont leur propre delai (`POSTURE_TIMEOUT_S`),
        le robot met plus de temps a acquitter « s'asseoir ».
        """
        connexion = self._connexion
        if connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        log.info("Commande envoyee au robot : %s", nom)
        api_id = nom if isinstance(nom, int) else (self._sport_cmd or {}).get(nom)
        if api_id is None:
            raise AdapterError(f"Commande inconnue : {nom}")
        demande = {"api_id": api_id}
        if parametre != "":
            demande["parameter"] = parametre

        try:
            reponse = await asyncio.wait_for(
                connexion.datachannel.pub_sub.publish_request_new(
                    self._rtc["SPORT_MOD"], demande
                ),
                timeout=self.COMMAND_TIMEOUT_S if timeout_s is None else timeout_s,
            )
        except asyncio.TimeoutError:
            return None
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(f"Commande « {nom} » refusée ({exc}).") from exc

        statut = ((reponse or {}).get("data") or {}).get("header", {}).get("status", {})
        code = statut.get("code")
        return int(code) if isinstance(code, (int, float)) else None

    # -- Préparation du programme -------------------------------------------

    def _prendre_la_main(self) -> None:
        """Reprend la main sur la vitesse du robot.

        Après un `StandUp`, le robot reste en « transition » (code d'état
        `1002`) : il attend que le client lui envoie une consigne de vitesse,
        même NULLE. Mesuré le 20/10/2026 : sans cette consigne, toutes les
        consignes de mouvement suivantes sont ignorées, et le robot reste
        planté en transition pendant des dizaines de secondes.

        La consigne nulle ne fait pas bouger le robot : elle lui dit
        simplement « c'est moi qui décide de la vitesse, et pour l'instant
        c'est zéro ».
        """
        self._envoyer_move(0.0, 0.0, 0.0)
        self._envoyer_sans_reponse("StopMove")

    async def _relever(self) -> bool:
        """Met le robot sur ses quatre pattes (usage interne).

        Renvoie `True` si la posture est acquittée ET tenue. Ne lève jamais :
        un refus ne doit pas empêcher le reste du programme.
        """
        try:
            resultat = await self._appliquer_posture("StandUp", Posture.STAND)
        except SafetyInterrupt:
            # Un arrêt de sécurité ne doit jamais être transformé en simple
            # « relèvement refusé » : le programme doit s'arrêter.
            raise
        except AdapterError as exc:
            log.warning("Relèvement refusé : %s", exc)
            return False
        if resultat.outcome != "exact":
            log.warning("Relèvement non obtenu : %s", resultat.detail)
            return False
        return True

    def _est_debout(self) -> bool:
        """Le robot est-il debout ?

        L'etat PUBLIE PAR LE ROBOT fait foi : `1013` (debout, immobile) ou
        `100` (en mouvement). C'est la seule source qui ne ment pas.

        ⚠️ La hauteur lue dans l'odometrie ne peut PAS servir de reference :
        pendant un mouvement violent, l'estimation s'emballe (0,52 m mesurés
        pendant un bond, pour un robot qui fait 0,32 m debout). Cette
        hauteur aberrante rendait le service convinced que le robot ne pouvait
        pas etre debout : il redemandait `StandUp` sans fin.

        En dernier recours, quand ni l'etat ni la mesure ne disent rien, on
        se rabat sur le dernier ordre de posture envoye.
        """
        code = self._code_etat
        if code is not None:
            return code in self.ETAT_PRET
        hauteur = self._position[2] if self._position else None
        reference = self._hauteur_max
        if hauteur is not None and reference is not None:
            return hauteur >= reference * self.SITUE_RATIO
        # Rien ne le dit : on ne suppose pas debout. Se lever est sans
        # conséquence ; partir en supposant le robot debout, non.
        return self._posture in (Posture.STAND, Posture.BALANCE)

    def _est_assis(self) -> bool:
        """Le robot est-il assis (et non allongé par terre) ?

        L'etat du robot d'abord (`1007`), la hauteur en repli, le dernier
        ordre de posture en dernier ressort.
        """
        code = self._code_etat
        if code is not None:
            return code == self.ETAT_ASSIS_CODE
        hauteur = self._position[2] if self._position else None
        reference = self._hauteur_max
        if hauteur is not None and reference is not None:
            return hauteur < reference * self.SITUE_RATIO and (
                hauteur >= reference * self.COCHE_RATIO
            )
        return self._posture is Posture.SIT

    def _est_alleonge(self) -> bool:
        """Le robot est-il allongé par terre (après un `Damp`) ?"""
        code = self._code_etat
        if code is not None:
            return code == self.ETAT_ALLOUGE_CODE
        hauteur = self._position[2] if self._position else None
        reference = self._hauteur_max
        if hauteur is not None and reference is not None:
            return hauteur < reference * self.COCHE_RATIO
        return self._posture is Posture.LIE_DOWN

    async def _attendre_pret(self, timeout_s: float | None = None) -> bool:
        """Attend que le robot soit capable de marcher.

        Le SDK publie un `error_code` dans l'etat du robot. Mesure faite sur
        la machine le 20/10/2026 :

        - `100` : debout, au repos ou en marche — le robot suit les consignes ;
        - `1002` : **transition de posture en cours** (il se relève) — le
          robot IGNORE les consignes de mouvement, et les lui envoyer
          l'empeche meme de terminer sa transition ;
        - `1007` : assis.

        C'est ce code, et non la seule stabilite de la hauteur, qui dit si le
        robot peut bouger : un robot dont la hauteur est stable peut encore
        etre en train de se relever.

        Sans code d'etat publie, on ne peut rien attendre de mesurable : on
        rend la main, et la stabilisation de la hauteur prend le relais.
        """
        limite = time.monotonic() + (
            timeout_s if timeout_s is not None else self.PRET_TIMEOUT_S
        )
        while time.monotonic() < limite:
            code = self._code_etat
            if code is None:
                return False
            if code in self.ETAT_PRET:
                return True
            await asyncio.sleep(self.STABLE_SAMPLE_S)
        return False

    async def _attendre_stable(self, timeout_s: float | None = None) -> bool:
        """Attend que le robot cesse de changer de hauteur.

        Une transition de posture dure plusieurs secondes. Toute commande
        envoyée pendant la transition est REFUSÉE par le robot : c'est
        ainsi qu'un « s'asseoir » demandé juste après un « se relever »
        se faisait silencieusement ignorer.

        La hauteur est lue dans l'état publié par le SDK. Sans mesure, on
        ne peut rien attendre de mesurable : on rend la main aussitôt.
        """
        limite = time.monotonic() + (
            timeout_s if timeout_s is not None else self.STABLE_TIMEOUT_S
        )
        precedent = self._position[2] if self._position else None
        stable = 0
        while time.monotonic() < limite:
            await asyncio.sleep(self.STABLE_SAMPLE_S)
            actuel = self._position[2] if self._position else None
            if actuel is None or precedent is None:
                return False
            if abs(actuel - precedent) < self.STABLE_HEIGHT_M:
                stable += 1
                if stable >= self.STABLE_SAMPLES:
                    return True
            else:
                stable = 0
            precedent = actuel
        return False

    async def prepare_run(self) -> None:
        """Met le robot sur ses quatre pattes AVANT le premier ordre.

        Pourquoi : le SDK relève de lui-même un robot assis quand il reçoit
        une consigne `Move`. C'est une commodité, pas une garantie : on le
        fait donc explicitement, et on le laisse écrire dans le journal.

        Le programme de l'enfant peut donc commencer par « avancer » sans
        qu'on doive expliquer pourquoi le robot se relevait tout seul.
        """
        if not self._connected or self._connexion is None:
            return
        # Un programme commence : c'est lui qui relève le robot s'il est
        # allongé, pas le relevage automatique.
        self._programme_en_cours = True
        self._allonge_demande = False
        # Le message du dernier relevé n'a plus lieu d'être.
        self._recovery_reason = None
        if self._securite.latched:
            # Ne pas simplement ignorer la préparation : le moteur doit
            # terminer en « safety », pas enchaîner sur le premier bloc.
            raise SafetyInterrupt(
                self._securite.reason
                or "Le robot est à l’arrêt pour une raison de sécurité."
            )
        if self._est_debout():
            # Déjà sur ses pattes : rien à demander.
            return
        log.info(
            "Robot non debout (posture %s, etat %s) : remise sur quatre pattes.",
            self._posture,
            self._code_etat,
        )
        await self._relever()

    # -- Pilotage manuel ----------------------------------------------------

    async def manual_prepare(self) -> None:
        """Prépare le robot pour le pilotage manuel.

        Le robot peut être assis quand l'adulte ouvre le mode manuel : il faut
        le relever avant la première consigne de vitesse. La préparation est
        faite une seule fois par session, pas à chaque touche.
        """
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        self._programme_en_cours = True
        self._allonge_demande = False
        self._recovery_reason = None
        self._refuser_si_secours()
        self._derniere_requete_lidar = time.monotonic()
        if not self._lidar_physique_actif and not self._en_veille:
            await self.set_lidar_switch(True)
        await self._se_preparer_a_bouger()
        self._refuser_si_secours()

    def manual_velocity(
        self, direction: str, speed_mps: float, turn_speed_rps: float
    ) -> None:
        """Envoie une consigne de vitesse manuelle, sans durée.

        La vitesse est fixée par le service, jamais par le navigateur. Le
        contrôleur `ManualControl` renouvelle l'ordre tant que la touche est
        tenue et envoie un arrêt immédiat au relâchement.
        """
        valid_directions = (
            "forward",
            "backward",
            "left",
            "right",
            "turn_left",
            "turn_right",
            "forward+turn_left",
            "forward+turn_right",
            "backward+turn_left",
            "backward+turn_right",
        )
        if direction not in valid_directions:
            raise AdapterError(f"Direction manuelle inconnue : {direction}")
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)
        self._refuser_si_secours()

        if self._crouch_mode:
            # Vitesse réduite en mode accroupi : déplacement fluide, lent et très stable
            speed_mps = min(speed_mps, 0.20)
            turn_speed_rps = min(turn_speed_rps, 0.50)

        vx = 0.0
        vy = 0.0
        vyaw = 0.0

        if "forward" in direction:
            vx = speed_mps
        elif "backward" in direction:
            vx = -speed_mps

        if "left" in direction and "turn" not in direction:
            vy = speed_mps
        elif "right" in direction and "turn" not in direction:
            vy = -speed_mps

        if "turn_left" in direction:
            vyaw = turn_speed_rps
        elif "turn_right" in direction:
            vyaw = -turn_speed_rps

        self._programme_en_cours = True
        self._state = RobotState.MOVING
        self._posture = Posture.STAND
        self._envoyer_move(vx, vy, vyaw)

    async def manual_session_end(self) -> None:
        """Fin de session manuelle : arrête le robot et réactive la gestion d'inactivité."""
        if self._crouch_mode:
            await self.exit_crouch_mode()
        self._programme_en_cours = False
        self._derniere_requete_lidar = time.monotonic()
        await self.request_stop()

    def manual_stop(self) -> None:
        """Arrête la vitesse manuelle sans terminer la session.

        Contrairement à `request_stop()`, on ne touche pas au drapeau
        `_programme_en_cours` : le relevage automatique reste désactivé tant
        que l'adulte n'a pas quitté le mode manuel.
        """
        if self._connexion is None:
            return
        if self._securite.latched or self._est_au_sol():
            return
        try:
            self._envoyer_move(0.0, 0.0, 0.0)
            self._envoyer_sans_reponse("StopMove")
        except Exception:  # noqa: BLE001
            pass
        self._state = RobotState.IDLE

    async def manual_jump(self) -> None:
        """Exécute un saut en mode manuel (sans flux de vitesse parasite)."""
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)
        self._refuser_si_secours()

        self._derniere_requete_lidar = time.monotonic()
        if not self._lidar_physique_actif and not self._en_veille:
            await self.set_lidar_switch(True)
        if not self._est_debout():
            await self._relever()
        self._refuser_si_secours()

        # Fenêtre de grâce pour que la perte d'appuis pendant le saut ne coupe pas les moteurs
        self._posture_grace_until = time.monotonic() + 3.5

        code = await self._commander("FrontJump", timeout_s=self.POSTURE_TIMEOUT_S)
        if code != 0:
            log.info("FrontJump code=%s, tentative FrontPounce", code)
            code = await self._commander("FrontPounce", timeout_s=self.POSTURE_TIMEOUT_S)

        self._posture = Posture.STAND
        await asyncio.sleep(0.5)
        self._prendre_la_main()

    # -- Mode Déplacement Accroupi (Crawl / Creep) -------------------------

    @property
    def crouch_mode_active(self) -> bool:
        """Indique si le mode accroupi (StaticWalk) est actif."""
        return self._crouch_mode

    async def enter_crouch_mode(self) -> None:
        """Active le mode accroupi : gait rampant (StaticWalk) et vitesse modérée."""
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)
        self._refuser_si_secours()

        # Le robot doit être debout et stable sur ses 4 pattes
        if not self._est_debout():
            await self._relever()
        self._refuser_si_secours()

        # Arrêt des vitesses en cours avant transition
        self._envoyer_move(0.0, 0.0, 0.0)
        self._envoyer_sans_reponse("StopMove")

        # Active le mode StaticWalk (1061) du Go2 (démarche rampante à 4 temps, stable et lente)
        code = await self._commander("StaticWalk", timeout_s=self.POSTURE_TIMEOUT_S)
        if code not in (0, None):
            log.info("StaticWalk code=%s, repli ClassicWalk", code)
            import json
            await self._commander("ClassicWalk", json.dumps({"data": True}), timeout_s=self.POSTURE_TIMEOUT_S)

        self._crouch_mode = True
        log.info("Mode accroupi (StaticWalk) activé.")

    async def exit_crouch_mode(self) -> None:
        """Désactive le mode accroupi avec retour progressif à la posture normale."""
        if not self._connected or self._connexion is None:
            self._crouch_mode = False
            return

        try:
            # 1. Arrêt de toute vitesse
            self._envoyer_move(0.0, 0.0, 0.0)
            self._envoyer_sans_reponse("StopMove")

            # 2. Rétablissement progressif de la posture debout normale via BalanceStand
            await self._commander("BalanceStand", timeout_s=self.POSTURE_TIMEOUT_S)
            import json
            await self._commander("ClassicWalk", json.dumps({"data": False}), timeout_s=self.POSTURE_TIMEOUT_S)
            await asyncio.sleep(0.5)
            self._prendre_la_main()
        except Exception as exc:  # noqa: BLE001
            log.warning("Erreur lors du retour à la posture normale : %s", exc)
        finally:
            self._crouch_mode = False
            log.info("Mode accroupi désactivé, retour à la posture normale terminé.")

    # -- Mode Autonome -----------------------------------------------------

    async def enter_autonomous_mode(self) -> None:
        """Active le mode autonome : prépare le robot et engage l'évitement d'obstacles."""
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)
        self._refuser_si_secours()

        if not self._est_debout():
            await self._relever()
        self._refuser_si_secours()

        self._envoyer_move(0.0, 0.0, 0.0)
        self._envoyer_sans_reponse("StopMove")

        self.obstacle_safety_enabled = True
        self._en_autonome = True

        try:
            import json
            # Envoi asynchrone direct sans bloquer 5 secondes sur un acquittement inexistant
            self._envoyer_sans_reponse("FreeAvoid", json.dumps({"data": True}))
        except Exception as exc:  # noqa: BLE001
            log.info("FreeAvoid échec d'envoi : %s", exc)

        self._prendre_la_main()
        log.info("Mode autonome physique activé.")

    async def exit_autonomous_mode(self) -> None:
        """Désactive le mode autonome et immobilise le robot."""
        self._en_autonome = False
        if not self._connected or self._connexion is None:
            return
        try:
            self._envoyer_move(0.0, 0.0, 0.0)
            self._envoyer_sans_reponse("StopMove")
            import json
            self._envoyer_sans_reponse("FreeAvoid", json.dumps({"data": False}))
            self._envoyer_sans_reponse("BalanceStand")
            self._prendre_la_main()
        except Exception as exc:  # noqa: BLE001
            log.warning("Erreur lors de la sortie du mode autonome : %s", exc)
        log.info("Mode autonome physique désactivé.")

    # -- Mode Veille -------------------------------------------------------

    def _eteindre_lumiere(self) -> None:
        """Éteint les voyants / phares (VUI) si disponibles pour économiser l'énergie."""
        connexion = self._connexion
        if connexion is None:
            return
        try:
            import json
            connexion.datachannel.pub_sub.publish_without_callback(
                topic=self._rtc["VUI"],
                data={"header": {"identity": {"id": 0, "api_id": 1005}}, "parameter": json.dumps({"brightness": 0})},
                msg_type=self._types_canal["REQUEST"],
            )
        except Exception:  # noqa: BLE001
            pass

    async def _eteindre_lidar(self) -> None:
        """Éteint le LiDAR et coupe les flux de données pour la veille."""
        connexion = self._connexion
        if connexion is None:
            return
        try:
            canal = connexion.datachannel.pub_sub

            # 1. Couper le trafic de voxels
            try:
                await connexion.datachannel.disableTrafficSaving(False)
            except Exception:  # noqa: BLE001
                pass

            # 2. Se désabonner des topics LiDAR pour arrêter la réception
            for topic_name in ("ULIDAR_ARRAY", "ULIDAR", "ULIDAR_STATE", "ROBOTODOM"):
                t = self._rtc.get(topic_name)
                if t:
                    try:
                        canal.unsubscribe(t)
                    except Exception:  # noqa: BLE001
                        pass

            # 3. Demander l'extinction du LiDAR physique sur rt/utlidar/switch
            t_switch = self._rtc.get("ULIDAR_SWITCH", "rt/utlidar/switch")
            try:
                canal.publish_without_callback(topic=t_switch, data="OFF")
                canal.publish_without_callback(topic=t_switch, data="off")
            except Exception:  # noqa: BLE001
                pass
            self._lidar_physique_actif = False

            # 4. Couper l'anti-obstacle interne Unitree
            t_oa = self._rtc.get("OBSTACLES_AVOID", "rt/api/obstacles_avoid/request")
            try:
                canal.publish_without_callback(
                    topic=t_oa,
                    data={
                        "header": {"identity": {"id": 0, "api_id": 1001}},
                        "parameter": json.dumps({"enable": False}),
                    },
                    msg_type=self._types_canal["REQUEST"],
                )
            except Exception:  # noqa: BLE001
                pass

            self._obstacles_lidar = []
            self._volume_lidar = None
            log.info("LiDAR éteint et flux arrêtés pour la veille.")
        except Exception as exc:  # noqa: BLE001
            log.info("Extinction du LiDAR impossible : %s", exc)

    async def enter_standby(self) -> None:
        """Passe le robot en mode veille économique (mode couché).

        0. Vérifie que le robot est bien debout sur ses 4 pattes : s'il est assis ou
           dans une autre posture, le relève d'abord pour garantir une descente symétrique.
        1. Coupe toute vitesse résiduelle.
        2. Fait coucher doucement le robot sous contrôle moteur via StandDown (1005).
           (On n'utilise PAS Damp pour éviter que le robot ne tombe).
        3. Attend que le robot soit totalement posé au sol et stable (z < 0.12m).
        4. Éteint le LiDAR et coupe les voyants/capteurs superflus.
        """
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)
        self._refuser_si_secours()

        self._en_veille = True
        log.info("Début de la mise en veille progressive du robot (mode couché)...")

        # Arrêt immédiat de toute marche en cours
        try:
            self._envoyer_move(0.0, 0.0, 0.0)
            self._envoyer_sans_reponse("StopMove")
        except Exception:  # noqa: BLE001
            pass

        # 0. S'assurer que le robot est bien debout sur ses 4 pattes avant de se coucher.
        # S'il est assis ou dans une posture intermédiaire, StandDown risquerait d'être asymétrique.
        if not self._est_debout():
            log.info(
                "Robot non debout (%s) : relèvement préalable sur ses 4 pattes avant la mise en veille...",
                self._posture.value if self._posture else "inconnu",
            )
            self._posture_grace_until = time.monotonic() + 4.0
            try:
                await self._commander("StandUp", timeout_s=self.POSTURE_TIMEOUT_S)
                await self._attendre_debout(timeout_s=self.PRET_TIMEOUT_S)
                await asyncio.sleep(0.5)
                self._posture = Posture.STAND
            except Exception as exc:
                log.warning("Relèvement préalable avant mise en veille : %s", exc)

        # 1. Coucher en douceur sous contrôle moteur (StandDown 1005)
        # StandDown plie les pattes de manière synchronisée et dépose le corps au sol en douceur sans aucune chute.
        self._posture_grace_until = time.monotonic() + 10.0
        self._allonge_demande = True
        try:
            log.info("Coucher en douceur du robot via StandDown (1005)...")
            await self._commander("StandDown", timeout_s=self.POSTURE_TIMEOUT_S)
        except Exception as exc:
            log.warning("Erreur commande StandDown : %s", exc)

        # 2. Attente que le robot soit bien au sol (couché)
        await self._attendre_alleonge(timeout_s=6.0)
        await asyncio.sleep(1.0)
        self._posture = Posture.LIE_DOWN

        # 3. Éteindre le LiDAR et couper la lumière une fois complètement au sol
        await self._eteindre_lidar()
        self._eteindre_lumiere()

        # 4. Bilan thermique
        t_info = []
        if self._temperature_ntc1 is not None:
            t_info.append(f"châssis {self._temperature_ntc1}°C")
        if self._motor_temp_max is not None:
            t_info.append(f"moteurs max {self._motor_temp_max}°C")
        details_temp = f" ({', '.join(t_info)})" if t_info else ""
        log.info(
            "Robot en veille : corps au sol, LiDAR éteint, moteurs au repos%s. "
            "Les ventilateurs ralentiront/s'éteindront automatiquement dès dissipation thermique.",
            details_temp,
        )

    async def exit_standby(self) -> None:
        """Sort le robot du mode veille et le remet debout.

        1. Rallume le LiDAR et réactive les capteurs.
        2. Relève le robot avec StandUp.
        3. Attend qu'il soit debout et stable.
        4. Reprend la main pour le rendre prêt à recevoir des commandes.
        """
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)
        self._refuser_si_secours()

        log.info("Début du réveil progressif du robot...")

        # 1. Réactivation du LiDAR
        await self._demarrer_lidar()

        # 2. Relever le robot
        self._posture_grace_until = time.monotonic() + 4.0
        try:
            code = await self._commander("StandUp", timeout_s=self.POSTURE_TIMEOUT_S)
            if code != 0:
                log.info("StandUp code=%s, attente de l'état debout...", code)
        except Exception as exc:
            log.exception("Erreur lors de la commande StandUp : %s", exc)

        # 3. Attente que le robot soit debout
        await self._attendre_debout(timeout_s=self.PRET_TIMEOUT_S)
        await asyncio.sleep(0.5)

        # 4. Reprise de la main (Move 0,0,0) pour quitter la transition (code 1002)
        self._prendre_la_main()
        await self._attendre_stable()

        self._posture = Posture.STAND
        self._en_veille = False
        log.info("Robot réveillé avec succès : debout, LiDAR réactivé, prêt.")

    # -- Execution ---------------------------------------------------------

    def _refuser_si_secours(self) -> None:
        """Refuse toute commande tant que le verrouillage est actif.

        `request_stop()` reste appelable, mais ne renvoie plus rien tant que
        le verrouillage est actif : le déclencheur a déjà envoyé l'arrêt et
        `Damp`.
        """
        if self._securite.latched:
            raise SafetyInterrupt(
                self._securite.reason
                or "Le robot est à l’arrêt pour une raison de sécurité."
            )

    async def execute_command(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        # L'arrêt reste toujours permis. Toute autre instruction est refusée
        # tant que le robot n'est pas de nouveau stable sur ses appuis.
        if command.kind is not CommandKind.STOP:
            self._refuser_si_secours()

        match command.kind:
            case CommandKind.WAIT:
                return await self._do_wait(command.seconds, index, should_stop)
            case CommandKind.STAND_UP:
                return await self._do_posture("StandUp", Posture.STAND, index)
            case CommandKind.SIT_DOWN:
                # S'assurer d'être debout sur ses 4 pattes avant de s'asseoir (ex: depuis couché)
                if not self._est_debout():
                    log.info(
                        "Robot non debout (%s) avant s'asseoir : relèvement préalable sur quatre pattes.",
                        self._posture,
                    )
                    await self._relever()
                return await self._do_posture("Sit", Posture.SIT, index)
            case CommandKind.STOP:
                await self.request_stop()
                return CommandOutcome(
                    index=index, outcome="exact", detail="Arrêt exécuté."
                )
            case CommandKind.FINGER_HEART:
                return await self._do_geste("FingerHeart", index)
            case CommandKind.SALUTE:
                return await self._do_geste("Hello", index)
            case CommandKind.STRETCH:
                return await self._do_geste("Stretch", index)
            case CommandKind.FRONT_JUMP:
                # Saut : pas de flux de vitesse (qui écraserait l'impulsion motrice par
                # des Move(0,0,0) concurrents) et grâce temporelle pour les appuis.
                self._posture_grace_until = time.monotonic() + 3.5
                outcome = await self._do_geste("FrontJump", index, flux_vitesse=False)
                if outcome.outcome != "exact":
                    log.info("FrontJump non exact (%s), repli sur FrontPounce", outcome.outcome)
                    outcome = await self._do_geste("FrontPounce", index, flux_vitesse=False)
                return outcome
            case CommandKind.LIE_DOWN:
                # S'assurer d'être debout sur ses 4 pattes avant de se coucher (ex: depuis assis)
                # pour éviter toute chute ou déséquilibre.
                if not self._est_debout():
                    log.info(
                        "Robot non debout (%s) avant de se coucher : relèvement préalable sur quatre pattes.",
                        self._posture,
                    )
                    await self._relever()
                # `Damp` : le robot s'allonge (il ne se déplace plus).
                # Pas de flux de vitesse : on veut qu'il se pose.
                return await self._do_geste(
                    "Damp",
                    index,
                    lever_si_assis=True,
                    reprendre_la_main=False,
                    flux_vitesse=False,
                )
            case _:
                return await self._do_move(command, index, should_stop)

    async def _do_wait(
        self, seconds: float, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        restant = max(0.0, seconds)
        while restant > 0:
            self._refuser_si_secours()
            if should_stop.requested:
                return CommandOutcome(index=index, outcome="stopped")
            await asyncio.sleep(min(0.05, restant))
            restant -= 0.05
        self._refuser_si_secours()
        return CommandOutcome(index=index, outcome="exact")

    async def _attendre_posture(
        self, posture: Posture, timeout_s: float | None = None
    ) -> bool:
        """Attend que le robot PUBLIE la posture demandée.

        Le code d'état est la seule preuve : `1007` assis, `1013`/`100`
        debout, `1001` allongé. On l'interroge toutes les 100 ms, et on
        abandonne après `timeout_s`.

        Cette attente existe parce que l'acquittement d'une posture peut
        se perdre : le robot s'assoit quand meme, et c'est son etat publie
        qui dit la verite.
        """
        if timeout_s is None:
            timeout_s = self.POSTURE_ATTENTE_S
        fin = time.monotonic() + timeout_s
        while time.monotonic() < fin:
            if self._posture_tenue(posture):
                return True
            await asyncio.sleep(0.1)
        return self._posture_tenue(posture)

    async def _attendre_alleonge(self, timeout_s: float | None = None) -> bool:
        """Attend que le robot PUBLIE qu'il est allongé (`1001`).

        C'est la preuve qu'il s'est réellement couché. Une commande peut
        être acquittée et rester sans effet : le robot est alors occupé par
        autre chose (un geste, par exemple).
        """
        if timeout_s is None:
            timeout_s = self.COUCHER_ATTENTE_S
        fin = time.monotonic() + timeout_s
        while time.monotonic() < fin:
            if self._est_alleonge():
                return True
            await asyncio.sleep(0.1)
        return self._est_alleonge()

    def _est_au_sol(self) -> bool:
        """Le robot est-il au sol, ou en train de s'y poser ?

        Dans ces cas, on n'envoie **aucune** consigne de vitesse : sur un Go2,
        `Move` et `StopMove` relèvent le robot.

        Le troisième cas (transition vers la position assise, code `1006`) a
        été ajouté après le 21/10/2026 : l'arrêt de fin de programme
        arrivait pendant la pose et relevait le chien.
        """
        if self._est_assis() or self._est_alleonge():
            return True
        return self._code_etat == self.ETAT_TRANSITION_ASSIS

    def _posture_tenue(self, posture: Posture) -> bool:
        """La posture demandée est-elle réellement tenue ?

        L'etat publie par le robot fait foi :
        `1013`/`100` = debout, `1007` = assis, `1001` = allongé par terre.

        Sans code d'etat, on se rabat sur la hauteur lue dans l'etat — et
        seulement alors, car l'odometrie s'emballe pendant un mouvement.
        """
        code = self._code_etat
        if code is not None:
            if posture is Posture.STAND:
                return code in self.ETAT_PRET
            if posture is Posture.SIT:
                return code == self.ETAT_ASSIS_CODE
            if posture is Posture.LIE_DOWN:
                return code == self.ETAT_ALLOUGE_CODE
            return True

        hauteur = self._position[2] if self._position else None
        reference = self._hauteur_max
        if hauteur is None or reference is None:
            return True
        if posture is Posture.LIE_DOWN:
            return hauteur < reference * self.COCHE_RATIO
        if posture is Posture.SIT:
            return hauteur < reference * self.SITUE_RATIO
        return hauteur >= reference * self.SITUE_RATIO

    async def _appliquer_posture(
        self, nom: str, posture: Posture
    ) -> CommandOutcome:
        """Demande une posture, et vérifie qu'elle est TENUE.

        Le robot peut acquitter la commande et se relever aussitôt (il
        l'a fait après une rotation). On vérifie donc la hauteur après la
        stabilisation, et on recommence une fois si la posture n'a pas tenu.

        Après un « se relever », on reprend la main sur la vitesse : c'est
        la consigne NULLE qui fait sortir le robot de sa transition, sans
        laquelle il ignorerait tous les mouvements du programme.
        """
        dernier_code: int | None = None
        self._refuser_si_secours()
        if posture in (Posture.STAND, Posture.SIT, Posture.LIE_DOWN):
            # Les pieds peuvent se décharger avant que l'état du robot ne
            # publie la posture finale. Cette fenêtre couvre la transition,
            # y compris le relèvement depuis la position assise.
            self._posture_grace_until = time.monotonic() + self.POSTURE_GRACE_S
        for essai in range(2):
            self._refuser_si_secours()
            code = await self._commander(nom, timeout_s=self.POSTURE_TIMEOUT_S)
            self._refuser_si_secours()
            if code is None:
                # Pas de reponse dans le delai. Pour une POSTURE, l'etat
                # PUBLIE par le robot (`1007` assis, `1013`/`100` debout) est
                # une preuve plus solide que la reponse : on attend la
                # posture au lieu de conclure a un echec. Le robot s'assoit
                # bien, meme si l'acquittement s'est perdu.
                if await self._attendre_posture(posture):
                    self._posture = posture
                    return CommandOutcome(
                        index=0,
                        outcome="exact",
                        detail="Le robot a publié la posture demandée (mesure).",
                    )
                return CommandOutcome(
                    index=0,
                    outcome="timeout",
                    detail="Le robot n’a pas acquitté la commande de posture.",
                )
            if code != 0:
                # Le robot refuse une posture pendant une transition.
                # On attend qu'il soit immobile, puis on réessaie.
                log.info(
                    "Posture %s refusee (code %s) : on attend la stabilisation.",
                    nom,
                    code,
                )
                dernier_code = code
                if await self._attendre_stable():
                    continue
                return CommandOutcome(
                    index=0,
                    outcome="failed",
                    detail=f"Le robot a refusé la posture (code {code}).",
                )

            self._posture = posture
            # On attend la fin de la transition : une commande envoyée
            # pendant que le robot se pose serait refusée.
            await self._attendre_stable()
            self._refuser_si_secours()

            if posture is Posture.STAND:
                # Reprendre la main sur la vitesse : c'est la consigne NULLE
                # qui fait sortir le robot de sa transition. On attend ensuite
                # l'état « pret » : c'est lui, et lui seul, qui dit que le
                # robot est vraiment debout.
                self._prendre_la_main()
                if not await self._attendre_pret():
                    log.info("Le robot ne signale pas son retour a l'etat pret.")

            if not self._posture_tenue(posture):
                # La posture n'est pas encore publiee : on lui laisse le
                # temps de s'etablir avant de reessayer. Mesuré le
                # 21/10/2026 : le robot passe en `1006` (transition) puis en
                # `1007` (assis) quelques secondes apres la commande.
                if await self._attendre_posture(posture):
                    return CommandOutcome(
                        index=0,
                        outcome="exact",
                        detail="Le robot a publié la posture demandée (mesure).",
                    )
                log.info(
                    "Le robot n'a pas tenu la posture %s : on recommence.",
                    posture.value,
                )
                continue

            return CommandOutcome(
                index=0,
                outcome="exact",
                detail="Commande acquittée par le robot ; posture non mesurée.",
            )

        if dernier_code is not None:
            return CommandOutcome(
                index=0,
                outcome="failed",
                detail=f"Le robot a refusé la posture (code {dernier_code}).",
            )
        return CommandOutcome(
            index=0,
            outcome="failed",
            detail="Le robot n’a pas tenu la posture demandée.",
        )

    async def _flux_vitesse(self, duree_s: float) -> None:
        """Parle au robot en vitesse, comme le fait l'application mobile.

        L'application officielle envoie une consigne de vitesse EN CONTINU,
        même quand le joystick est centré. Le robot reste alors dans l'état
        « en mouvement » (code `100`), et c'est dans cet état qu'il exécute
        les commandes de corps.

        Sans ce flux, le robot est « debout et immobile » (code `1013`) et la
        commande se rabat sur un simple coup de patte.

        La consigne est NULLE : le robot ne bouge pas, il reste simplement
        à l'écoute.
        """
        fin = time.monotonic() + duree_s
        while time.monotonic() < fin:
            if self._securite.latched:
                return
            self._envoyer_move(0.0, 0.0, 0.0)
            await asyncio.sleep(self.MOVE_REFRESH_S)

    async def _do_geste(
        self,
        nom: str,
        index: int,
        *,
        lever_si_assis: bool = True,
        reprendre_la_main: bool = True,
        flux_vitesse: bool = True,
    ) -> CommandOutcome:
        """Un geste du corps : cœur, saut, salut ou étirement.

        `lever_si_assis` : le geste suppose le robot debout, on se relève
        d'abord. L'allongement, lui, part de n'importe quelle position.

        `reprendre_la_main` : après le geste, on renvoie une consigne de
        vitesse NULLE, sans quoi le robot resterait en transition et
        ignorerait les mouvements suivants. Un robot allongé n'en a pas
        besoin : il ne bougera plus.

        `flux_vitesse` : on parle au robot en vitesse pendant le geste (voir
        `_flux_vitesse`). C'est ce qui fait que le robot EXÉCUTE le coup de
        patte au lieu de le transformer en simple coup de pied.
        """
        if lever_si_assis and not self._est_debout():
            await self._relever()
        self._refuser_si_secours()
        if nom in ("Damp", "FrontJump", "FrontPounce"):
            # « Se coucher » ou saut : le robot se relâche ou décolle, ses pieds
            # se déchargent temporairement sans qu'il ne s'agisse d'un portage.
            self._posture_grace_until = time.monotonic() + (
                3.5 if nom in ("FrontJump", "FrontPounce") else self.POSTURE_GRACE_S
            )
            if nom == "Damp":
                # C'est nous qui l'allongeons : le relevage automatique s'y
                # applique (le lidar peut frotter le sol).
                self._allonge_demande = True

        flux: asyncio.Task[None] | None = None
        if flux_vitesse:
            flux = asyncio.create_task(self._flux_vitesse(4.0))
            # Le temps que le robot passe en « en mouvement ».
            await asyncio.sleep(0.8)

        try:
            self._refuser_si_secours()
            code = await self._commander(
                nom,
                # Un geste met le robot en mouvement : il acquitte APRÈS
                # l'avoir exécuté (6,5 s mesurés pour « faire un cœur » le
                # 21/10/2026). Avec le délai court de 3 s, le service
                # abandonnait le geste et envoyait l'instruction SUIVANTE
                # pendant que le robot faisait encore son geste : celle-ci
                # était alors avalée.
                timeout_s=self.POSTURE_TIMEOUT_S,
            )
        except SafetyInterrupt:
            raise
        except AdapterError as exc:
            raise AdapterError(f"Le robot n’a pas acquitté le geste : {exc}") from exc
        finally:
            if flux is not None:
                flux.cancel()

        self._refuser_si_secours()

        if code is None:
            return CommandOutcome(
                index=index,
                outcome="timeout",
                detail="Le robot n’a pas acquitté la commande de geste.",
            )
        if code != 0:
            return CommandOutcome(
                index=index,
                outcome="failed",
                detail=f"Le robot a refusé le geste (code {code}).",
            )

        # Le geste dure quelques secondes : on attend la fin du mouvement.
        await self._attendre_stable()
        self._refuser_si_secours()

        if nom == "Damp":
            # « Se coucher » : on vérifie que le robot est bien allongé.
            # La commande peut être avalée si le robot vient de faire un
            # geste (il est encore en mouvement). On réessaie une fois.
            if not await self._attendre_alleonge():
                log.info("Le robot ne s'est pas allongé : on réessaie.")
                try:
                    await self._commander(nom, timeout_s=self.POSTURE_TIMEOUT_S)
                except AdapterError as exc:
                    log.warning("Se coucher : commande refusée (%s).", exc)
                if not await self._attendre_alleonge():
                    return CommandOutcome(
                        index=index,
                        outcome="timeout",
                        detail="Le robot n’a pas voulu s’allonger.",
                    )
                self._posture = Posture.LIE_DOWN
        elif nom == "FingerHeart":
            self._posture = Posture.SIT
        else:
            self._posture = Posture.STAND

        if reprendre_la_main:
            self._prendre_la_main()
            if not await self._attendre_pret():
                log.info("Le robot ne signale pas son retour a l'etat pret.")
        return CommandOutcome(
            index=index,
            outcome="exact",
            detail="Geste exécuté ; le robot n’a rien mesuré.",
        )

    async def _do_posture(
        self, nom: str, posture: Posture, index: int
    ) -> CommandOutcome:
        resultat = await self._appliquer_posture(nom, posture)
        return CommandOutcome(
            index=index,
            outcome=resultat.outcome,
            detail=resultat.detail,
        )

    async def _se_preparer_a_bouger(self) -> None:
        """Vérifie que le robot peut recevoir une consigne de mouvement.

        ⚠️ Le test `code not in ETAT_PRET` est essentiel : `ETAT_PRET` est un
        ENSEMBLE. Comparer `self._code_etat != self.ETAT_PRET` était toujours
        vrai (un entier n'est jamais égal à un ensemble), donc chaque
        déplacement attendait la stabilisation de la hauteur — jusqu'à six
        secondes — avant même d'envoyer sa première consigne. C'était l'une
        des causes du décalage entre durée demandée et durée réelle.
        """
        if not self._est_debout():
            await self._relever()
        self._refuser_si_secours()

        code = self._code_etat
        if code is not None and code not in self.ETAT_PRET:
            if code == self.ETAT_ASSIS:
                await self._relever()
            else:
                log.info(
                    "Robot en etat %s : on attend qu'il soit pret a bouger.",
                    code,
                )
                # Transition en cours : on attend la fin du redressement,
                # puis on reprend la main sur la vitesse. Sans cette
                # consigne nulle, le robot resterait en transition et
                # ignorerait le mouvement.
                await self._attendre_stable()
                self._prendre_la_main()
            if not await self._attendre_pret():
                raise AdapterError(
                    "Le robot n’est pas prêt à bouger : il est encore en "
                    "transition de posture.",
                    recoverable=True,
                )
            self._refuser_si_secours()

    async def _do_move(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        plan = plan_command(command, self._limits)
        if plan is None:
            raise AdapterError(f"Commande non gérée : {command.kind.value}")

        # Un déplacement suppose le robot debout et prêt. Le SDK le relèverait
        # de lui-même ; on le fait explicite, pour ne pas laisser le mouvement
        # dépendre d'un effet de bord.
        await self._se_preparer_a_bouger()
        self._refuser_si_secours()

        # Dernier point de controle avant que la valeur n'atteigne le canal.
        assert_speed_within_limits(plan, self._limits)

        if plan.angle_deg > 0:
            return await self._tourner(plan, index, should_stop)
        return await self._translater(plan, index, should_stop)

    async def _translater(
        self, plan: MotionPlan, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        """Tient la vitesse demandée pendant la durée demandée, puis s'arrête.

        C'est la seule façon d'obtenir « 1 seconde = 1 seconde » : le SDK ne
        connaît que `Move(vx, vy, vyaw)`, une VITESSE persistante. On la
        rafraîchit pendant exactement `plan.nominal_duration_s`, mesurée sur
        l'horloge murale, puis on envoie l'arrêt.

        Pourquoi pas `ecoule += 0.05` ? Parce que chaque `await` peut durer
        plus que 50 ms (réseau, boucle chargée) : l'accumulation dérivait, et
        une consigne de 1 s pouvait être tenue 5,7 s. L'horloge murale, elle,
        ne dérive pas.
        """
        direction = motion_direction(
            plan.linear_speed_mps, plan.lateral_speed_mps
        )
        vitesse = abs(plan.linear_speed_mps) + abs(plan.lateral_speed_mps)

        # Un relevé peut avoir lieu juste avant ce bloc : le lidar ne publie
        # sa carte que debout. On lui laisse le temps de republier, puis on
        # refait le contrôle ici, APRÈS la remise sur pattes. Le moteur a déjà
        # fait un premier contrôle, mais il pouvait manquer de carte.
        # Sécurité lidar coupée : on ne dépend plus de la carte pour partir.
        if self.obstacle_safety_enabled:
            await self._attendre_carte_lidar()
        if (
            self.obstacle_safety_enabled
            and direction is not None
            and vitesse > 0.0
        ):
            libre = await self.clearance_m(direction)
            if libre is not None:
                requis = required_clearance_m(
                    vitesse * plan.nominal_duration_s, direction
                )
                if libre < requis:
                    detail = obstacle_message(direction, libre)
                    log.info(
                        "Translation non faite : %s (libre %.2f m, requis %.2f m)",
                        detail,
                        libre,
                        requis,
                    )
                    return CommandOutcome(
                        index=index, outcome="blocked", detail=detail
                    )

        depart_xy = (
            (self._position[0], self._position[1]) if self._position else None
        )
        self._state = RobotState.MOVING
        log.info(
            "Translation : vitesse %.2f / %.2f m/s pendant %.2f s",
            plan.linear_speed_mps,
            plan.lateral_speed_mps,
            plan.nominal_duration_s,
        )

        # Le contrôle initial a eu lieu ci-dessus, avant la première consigne.
        # On laisse ensuite 0,1 s s'écouler avant de revérifier : inutile de
        # relire la même carte deux fois de suite.
        dernier_controle = time.monotonic()

        debut: float | None = None
        dernier_envoi = 0.0
        resultat = "exact"
        motif: str | None = None
        securite: str | None = None
        try:
            while True:
                if should_stop is not None and should_stop.requested:
                    resultat = "stopped"
                    break

                if self._securite.latched:
                    resultat = "stopped"
                    securite = (
                        self._securite.reason
                        or "Le robot s’est arrêté pour sa sécurité."
                    )
                    break

                maintenant = time.monotonic()

                # La carte peut changer pendant le déplacement (une personne
                # passe, une porte s'ouvre). On revérifie donc la place libre
                # à 10 Hz, et on arrête AVANT le contact.
                if (
                    self.obstacle_safety_enabled
                    and direction is not None
                    and vitesse > 0.0
                    and maintenant - dernier_controle >= self.OBSTACLE_CHECK_S
                ):
                    dernier_controle = maintenant
                    libre = await self.clearance_m(direction)
                    if libre is not None:
                        restant = (
                            plan.nominal_duration_s
                            if debut is None
                            else max(
                                0.0,
                                debut + plan.nominal_duration_s - maintenant,
                            )
                        )
                        requis = required_clearance_m(vitesse * restant, direction)
                        if libre < requis:
                            resultat = "stopped"
                            motif = obstacle_stop_message(direction)
                            log.warning(
                                "Obstacle %s : %.2f m libres, %.2f m "
                                "nécessaires pour finir le déplacement.",
                                direction,
                                libre,
                                requis,
                            )
                            break

                if debut is None:
                    self._envoyer_move(
                        plan.linear_speed_mps,
                        plan.lateral_speed_mps,
                        plan.angular_speed_rps,
                    )
                    debut = maintenant
                    dernier_envoi = maintenant
                    log.info(
                        " Premiere consigne Move : x=%.2f y=%.2f z=%.2f m/s",
                        plan.linear_speed_mps,
                        plan.lateral_speed_mps,
                        plan.angular_speed_rps,
                    )
                elif maintenant - dernier_envoi >= self.MOVE_REFRESH_S:
                    # `Move` est une consigne persistante : la rafraîchir
                    # évite qu'un état interne du robot ne l'oublie.
                    self._envoyer_move(
                        plan.linear_speed_mps,
                        plan.lateral_speed_mps,
                        plan.angular_speed_rps,
                    )
                    dernier_envoi = maintenant

                if maintenant - debut >= plan.nominal_duration_s:
                    break

                etat = await self.get_status()
                if not etat.connected or etat.blocked_reason:
                    raise AdapterError(
                        "Liaison perdue pendant le déplacement.", recoverable=True
                    )
                if self._code_etat in (
                    self.ETAT_ASSIS_CODE,
                    self.ETAT_ALLOUGE_CODE,
                ):
                    resultat = "failed"
                    motif = "Le robot s’est arrêté avant la fin du déplacement."
                    break

                if maintenant - debut >= plan.timeout_s:
                    resultat = "timeout"
                    motif = (
                        "Le délai de sécurité est atteint avant la fin de la "
                        "durée demandée."
                    )
                    break

                reste = debut + plan.nominal_duration_s - maintenant
                await asyncio.sleep(min(self.MOVE_LOOP_S, max(0.0, reste)))
        finally:
            # Toute sortie, y compris une exception, repasse par l'arrêt.
            await self.request_stop()

        # L'arrêt est envoyé ; on laisse au robot le temps de s'immobiliser
        # avant de lire la position. Le bloc suivant ne démarre qu'après.
        await asyncio.sleep(self.STOP_SETTLE_S)
        if securite is None and self._securite.latched:
            # Le verrouillage a pu être posé juste après la dernière lecture
            # de la boucle : la fin de ce pas doit tout de même être signalée
            # comme une sécurité, pas comme un succès.
            securite = (
                self._securite.reason
                or "Le robot s’est arrêté pour sa sécurité."
            )
        if securite is not None:
            raise SafetyInterrupt(securite)
        return self._bilan_distance(index, depart_xy, resultat, motif)

    async def _tourner(
        self, plan: MotionPlan, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        """Asservit la rotation sur le cap MESURÉ.

        Le SDK ne sait pas « tourner de 45° » : on lui donne une vitesse
        angulaire. Pour que 45° demandés fassent 45° réels, on lit le cap
        cumulé à chaque message d'état et on réduit la vitesse à mesure que
        l'écart diminue. Sous `YAW_BANDE_MORTE_DEG`, on arrête.

        Sans cap mesuré, on REFUSE la rotation : une rotation à l'aveugle est
        précisément ce qui produisait 139° pour 90° demandés.
        """
        maintenant = time.monotonic()
        if self._cap_cumule is None or self._cap_mesure_at is None:
            raise AdapterError(
                "Le cap du robot n’est pas mesuré : rotation refusée.",
                recoverable=True,
            )
        if maintenant - self._cap_mesure_at > self.STATE_STALE_S:
            raise AdapterError(
                "Le cap du robot n’est plus mesuré : rotation refusée.",
                recoverable=True,
            )

        signe = 1.0 if plan.angular_speed_rps >= 0.0 else -1.0
        depart = self._cap_cumule
        cible = signe * math.radians(plan.angle_deg)
        vitesse_max = (
            abs(plan.angular_speed_rps) or self._limits.motion.max_angular_speed
        )

        self._state = RobotState.MOVING
        log.info(
            "Rotation : %.1f degres vers %s, vitesse max %.2f rad/s",
            plan.angle_deg,
            "la gauche" if signe > 0 else "la droite",
            vitesse_max,
        )

        debut = time.monotonic()
        dernier_envoi = 0.0
        parcouru = 0.0
        resultat = "exact"
        motif: str | None = None
        securite: str | None = None
        try:
            while True:
                if should_stop is not None and should_stop.requested:
                    resultat = "stopped"
                    break

                if self._securite.latched:
                    resultat = "stopped"
                    securite = (
                        self._securite.reason
                        or "Le robot s’est arrêté pour sa sécurité."
                    )
                    break

                maintenant = time.monotonic()
                if (
                    self._cap_mesure_at is None
                    or maintenant - self._cap_mesure_at > self.STATE_STALE_S
                ):
                    raise AdapterError(
                        "Le cap du robot n’est plus mesuré : rotation interrompue.",
                        recoverable=True,
                    )

                parcouru = (
                    (self._cap_cumule if self._cap_cumule is not None else depart)
                    - depart
                )
                # `ecart` porte le SIGNE de la correction : positif si le
                # robot doit encore tourner dans le sens demandé, négatif
                # s'il a dépassé la cible.
                ecart = math.degrees(cible - parcouru)
                # Arrêt dès que la cible est atteinte ou franchie dans le sens demandé,
                # ou dès qu'on entre dans la bande morte. Élimine l'oscillation et le timeout.
                if (
                    abs(ecart) <= YAW_BANDE_MORTE_DEG
                    or (signe > 0.0 and ecart <= 0.0)
                    or (signe < 0.0 and ecart >= 0.0)
                ):
                    break

                periode_envoi = (
                    0.05 if abs(ecart) <= 25.0 else self.MOVE_REFRESH_S
                )
                if (
                    dernier_envoi == 0.0
                    or maintenant - dernier_envoi >= periode_envoi
                ):
                    vitesse = yaw_rate_for_remaining(abs(ecart), min(vitesse_max, 1.0))
                    self._envoyer_move(0.0, 0.0, math.copysign(vitesse, ecart))
                    dernier_envoi = maintenant

                if maintenant - debut >= plan.timeout_s:
                    resultat = "timeout"
                    motif = (
                        "Le délai de sécurité est atteint sans que le cap ait "
                        "rejoint la cible."
                    )
                    break

                await asyncio.sleep(self.MOVE_LOOP_S)
        finally:
            # Toute sortie, y compris une exception, repasse par l'arrêt.
            await self.request_stop()

        # Le cap continue de bouger quelques dixièmes de seconde après
        # `StopMove`. On lit donc l'angle APRÈS stabilisation : c'est lui que
        # l'interface affiche, et il doit décrire le robot arrêté.
        await asyncio.sleep(self.ROTATION_SETTLE_S)
        if self._cap_cumule is not None:
            parcouru = self._cap_cumule - depart
        if securite is None and self._securite.latched:
            # Même raison que pour la translation : aucun pas ne doit finir
            # en « réussi » si le verrouillage a été posé pendant l'arrêt.
            securite = (
                self._securite.reason
                or "Le robot s’est arrêté pour sa sécurité."
            )
        if securite is not None:
            raise SafetyInterrupt(securite)
        return self._bilan_angle(index, parcouru, resultat, motif)

    def _bilan_distance(
        self,
        index: int,
        depart_xy: tuple[float, float] | None,
        resultat: str,
        motif: str | None = None,
    ) -> CommandOutcome:
        """Résultat d'une translation : la durée est tenue, la distance est lue."""
        if depart_xy is not None and self._position is not None:
            mesure = travelled_distance_cm(
                depart_xy, (self._position[0], self._position[1])
            )
            return CommandOutcome(
                index=index,
                outcome=resultat,
                measured_distance_cm=round(mesure, 1),
                detail=motif
                or "Durée tenue ; distance lue dans l’odométrie après l’arrêt.",
            )
        return CommandOutcome(
            index=index,
            outcome=resultat,
            detail=motif or "Durée tenue ; aucune position mesurée.",
        )

    def _bilan_angle(
        self,
        index: int,
        parcouru_rad: float,
        resultat: str,
        motif: str | None = None,
    ) -> CommandOutcome:
        """Résultat d'une rotation : l'angle vient du cap mesuré, jamais du plan."""
        return CommandOutcome(
            index=index,
            outcome=resultat,
            measured_angle_deg=round(math.degrees(abs(parcouru_rad)), 1),
            detail=motif
            or "Angle lu dans le cap du robot après stabilisation.",
        )

    # -- Camera -------------------------------------------------------------

    async def camera_frame(self) -> bytes | None:
        """Derniere image de la camera du robot, en JPEG.

        `None` quand la camera n'est pas branchée ou n'a encore rien
        envoyé. Jamais une image inventée.

        Le canal video n'est ouvert qu'à la première demande : le décoder
        en continu alors que personne ne regarde coûtait un coeur entier.
        """
        self._camera_demande_at = time.monotonic()
        if not self._video_demarre:
            await self._demarrer_video()
        if self._dernier_jpeg is None and self._video_demarre:
            # La première image met quelques dixièmes de seconde à arriver.
            for _ in range(20):
                if self._dernier_jpeg is not None:
                    break
                await asyncio.sleep(0.1)
        return self._dernier_jpeg

    async def _demarrer_video(self) -> None:
        """Demande la camera du robot et garde la derniere image.

        Le SDK expose un canal video (`conn.video`) : on s'y abonne, et on
        garde la derniere image recue, encodee en JPEG.
        """
        connexion = self._connexion
        if connexion is None or self._video_demarre:
            return
        self._video_demarre = True
        try:
            video = connexion.video
            video.add_track_callback(self._lire_video)
            video.switchVideoChannel(True)
            log.info("Camera du robot demandee.")
        except Exception as exc:  # noqa: BLE001
            # Pas de camera n'est une degradee, pas une panne : le service
            # continue a piloter le robot.
            self._video_demarre = False
            log.info("Camera indisponible : %s", exc)

    async def _lire_video(self, track: Any) -> None:
        """Le SDK nous confie la piste video : on lit les images."""
        if self._tache_video is not None:
            return
        self._tache_video = asyncio.create_task(self._lire_images(track))

    async def _lire_images(self, track: Any) -> None:
        try:
            while True:
                image = await track.recv()
                maintenant = time.monotonic()
                # Personne ne regarde : on laisse tomber l'image sans
                # l'encoder. L'encodage JPEG etait le principal consommateur
                # du processeur quand la camera restait ouverte.
                if maintenant - self._camera_demande_at > self.CAMERA_ACTIVE_S:
                    continue
                if maintenant - self._dernier_jpeg_at < self.CAMERA_PERIODE_S:
                    continue
                self._dernier_jpeg_at = maintenant
                encodee = self._encoder_jpeg(image)
                if encodee:
                    self._dernier_jpeg = encodee
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.info("Flux camera interrompu : %s", exc)

    @staticmethod
    def _encoder_jpeg(image: Any) -> bytes | None:
        """Encode une image du robot en JPEG.

        PyAV (installé avec aiortc) sait multiplexer une image en JPEG
        sans passer par un fichier.
        """
        try:
            import av
        except ImportError:  # pragma: no cover - PyAV est une dependance de aiortc
            return None
        try:
            tampon = io.BytesIO()
            conteneur = av.open(tampon, mode="w", format="mjpeg")
            flux = conteneur.add_stream("mjpeg", rate=1)
            flux.width = image.width
            flux.height = image.height
            flux.pix_fmt = "yuvj420p"
            for paquet in flux.encode(image):
                conteneur.mux(paquet)
            conteneur.close()
            return tampon.getvalue()
        except Exception:  # noqa: BLE001
            return None

    # -- Lidar -------------------------------------------------------------

    async def _demarrer_lidar(self) -> None:
        """Allume le lidar du robot et s'abonne a sa carte.

        Le lidar publie une carte de voxels compressee, sur le sujet
        `rt/utlidar/voxel_map_compressed`. C'est ce que l'application mobile
        affiche quand on demande la vue « capteur ».
        """
        connexion = self._connexion
        if connexion is None:
            return
        try:
            canal = connexion.datachannel.pub_sub

            # 1. Réactiver la génération de trafic LiDAR
            try:
                await connexion.datachannel.disableTrafficSaving(True)
            except Exception:  # noqa: BLE001
                pass

            # 2. Réabonner les flux
            for topic_name in ("ULIDAR_ARRAY", "ULIDAR", "ULIDAR_STATE"):
                t = self._rtc.get(topic_name)
                if t:
                    canal.subscribe(t, self._sur_lidar)
            t_odom = self._rtc.get("ROBOTODOM")
            if t_odom:
                canal.subscribe(t_odom, self._sur_pose)

            # 3. Rallumer le LiDAR physique
            t_switch = self._rtc.get("ULIDAR_SWITCH", "rt/utlidar/switch")
            try:
                canal.publish_without_callback(topic=t_switch, data="ON")
                canal.publish_without_callback(topic=t_switch, data="on")
            except Exception:  # noqa: BLE001
                pass
            self._lidar_physique_actif = True
            self._derniere_requete_lidar = time.monotonic()

            # 4. Rétablir l'anti-obstacle interne Unitree
            t_oa = self._rtc.get("OBSTACLES_AVOID", "rt/api/obstacles_avoid/request")
            try:
                canal.publish_without_callback(
                    topic=t_oa,
                    data={
                        "header": {"identity": {"id": 0, "api_id": 1001}},
                        "parameter": json.dumps({"enable": True}),
                    },
                    msg_type=self._types_canal["REQUEST"],
                )
            except Exception:  # noqa: BLE001
                pass
            log.info("Lidar rallumé.")
        except Exception as exc:  # noqa: BLE001
            log.info("Lidar indisponible : %s", exc)

    def _sur_etat_lidar(self, donnees: dict[str, Any]) -> None:
        """Mémorise l'état du lidar : rotation, salissure, erreur.

        C'est le message `rt/utlidar/lidar_state`. Il porte l'état de la
        fenêtre tournante : quand elle frotte le sol, sa rotation réelle
        ralentit et le firmware peut signaler une erreur ou de la saleté.
        """
        erreur = donnees.get("error_state")
        salissure = donnees.get("dirty_percentage")
        sys_speed = donnees.get("sys_rotation_speed")
        com_speed = donnees.get("com_rotation_speed")
        ratio: float | None = None
        if (
            isinstance(com_speed, (int, float))
            and isinstance(sys_speed, (int, float))
            and sys_speed
        ):
            ratio = float(com_speed) / float(sys_speed)
            # Seules les rotations NORMALES entrent dans l'historique : un
            # blocage durable ne doit pas décaler la référence, sinon le
            # détecteur s'éteindrait de lui-même au bout de quelques
            # secondes.
            if self._rotation_normale(ratio):
                self._rotations.append(ratio)
        nouveau = {
            "erreur": erreur,
            "salissure": salissure,
            "rotation_sys": sys_speed,
            "rotation_com": com_speed,
            "ratio": round(ratio, 5) if ratio is not None else None,
        }
        # On ne journalise que ce qui change vraiment : l'IMU du lidar, lui,
        # bouge a chaque tour de tete.
        signature = (
            erreur,
            salissure,
            round(ratio, 4) if ratio is not None else None,
        )
        if signature != self._signature_lidar:
            self._signature_lidar = signature
            self._etat_lidar = nouveau
            self._etat_lidar_at = time.monotonic()
            log.info("Lidar : état %s", nouveau)

    def _sur_lidar(self, message: Any) -> None:
        """Une carte du lidar est arrivée.

        Le SDK décode la carte de voxels en un MAILLAGE : les sommets
        (`positions`) sont les coins des voxels occupés, repérés par leur
        indice dans la grille. On en tire la vue de dessus (x, y), celle
        que l'application affiche.
        """
        donnees = (message or {}).get("data") or {}
        if not isinstance(donnees, dict):
            donnees = {"data": donnees}
        sujet = (message or {}).get("topic", "?")
        if sujet not in self._lidar_vus:
            self._lidar_vus.add(sujet)
            resume = {
                cle: (f"<{len(valeur)} car.>" if isinstance(valeur, (str, bytes)) else valeur)
                for cle, valeur in donnees.items()
            }
            log.info("Lidar : premier message sur %s, structure %s", sujet, resume)

        if "error_state" in donnees:
            # C'est l'etat du lidar lui-meme, pas la carte : il dit si sa
            # fenetre tournante frotte quelque chose.
            self._sur_etat_lidar(donnees)
            return

        # Pendant un déplacement en bloc (ex. rotation), on allège le traitement
        # pour ne pas saturer l'event loop asyncio.
        # En revanche, en mode autonome, le traitement continu des obstacles lidar
        # est impératif pour assurer la détection et la trajectoire d'évitement.
        if self._state == RobotState.MOVING and not getattr(self, "_en_autonome", False):
            return

        if not self._lidar_physique_actif:
            return

        maintenant = time.monotonic()
        if maintenant - self._lidar_traite_at < self.LIDAR_TRAITEMENT_S:
            return
        self._lidar_traite_at = maintenant

        cells = self._cellules_2d(donnees)
        if cells:
            self._points_lidar = cells
            self._points_lidar_at = time.monotonic()
            if (
                self._lidar_compte_at is None
                or time.monotonic() - self._lidar_compte_at > 5
            ):
                self._lidar_compte_at = time.monotonic()
                log.info(
                    "Lidar : %d cases occupées autour du robot.", len(cells)
                )

        maillage = self._maillage_3d(donnees)
        if maillage is not None:
            self._volume_lidar = maillage
            self._volume_lidar_at = time.monotonic()
            if self._lidar_origine_at is None:
                self._lidar_origine_at = time.monotonic()
                log.info(
                    "Lidar : origine de la grille %s, robot a %s.",
                    maillage["origin"],
                    self._position,
                )

    def _maillage_3d(self, donnees: dict[str, Any]) -> dict[str, Any] | None:
        """Le volume de voxels, prêt à être dessiné en 3D.

        Le SDK livre un maillage dont les sommets sont les INDICES des
        voxels dans la grille (0..127), trois par sommet. On en tire les
        cases occupées (les sommets d'un même cube se répètent), et on les
        renvoie en base64 : c'est quelques kilo-octets pour toute la carte,
        au lieu de 200 Ko de JSON. Le navigateur reconstitue la grille.
        """
        mesh = donnees.get("data")
        if not isinstance(mesh, dict):
            return None
        positions = mesh.get("positions")
        origin = donnees.get("origin")
        resolution = donnees.get("resolution")
        if positions is None or origin is None or resolution is None:
            return None
        try:
            valeurs = positions.tolist() if hasattr(positions, "tolist") else list(positions)
        except (TypeError, ValueError):
            return None

        cases: set[tuple[int, int, int]] = set()
        for i in range(0, len(valeurs) - 2, 3):
            cases.add(
                (
                    int(valeurs[i]),
                    int(valeurs[i + 1]),
                    int(valeurs[i + 2]),
                )
            )
        if not cases:
            return None

        largeur = donnees.get("width") or [0, 0, 0]
        pas = float(resolution)
        # Ou est le robot, et vers quoi il regarde (pose « odom »).
        pose = self._pose_robot or {}

        # Les memes cases, mais sans le sol : c'est ce que le service
        # interroge avant chaque deplacement pour savoir s'il y a la place.
        origine = (float(origin[0]), float(origin[1]), float(origin[2]))
        self._obstacles_lidar = obstacle_cells(cases, origine, pas)
        self._obstacles_lidar_at = time.monotonic()

        octets = bytes(v for case in cases for v in case)
        return {
            "origin": [float(v) for v in origin],
            "resolution": pas,
            "largeur": [int(v) for v in largeur],
            "robot": {
                "x": round(float(pose.get("x", 0.0)), 3),
                "y": round(float(pose.get("y", 0.0)), 3),
                "cap": round(float(pose.get("cap", 0.0)), 4),
            },
            "positions": base64.b64encode(octets).decode("ascii"),
            "sommets": len(cases),
        }

    async def lidar_volume(self) -> dict[str, Any] | None:
        """Le volume de voxels du lidar, pour la vue en 3D.

        `None` quand le lidar n'a rien envoyé : on n'invente pas de carte.
        """
        self._derniere_requete_lidar = time.monotonic()
        if not self._lidar_physique_actif and not self._en_veille:
            await self.set_lidar_switch(True)
        if not self._volume_lidar:
            return None
        if time.monotonic() - self._volume_lidar_at > self.LIDAR_PERIME_S:
            return None
        return self._volume_lidar

    def _cellules_2d(self, donnees: dict[str, Any]) -> list[list[float]] | None:
        """Les cases occupées de la carte, vues du dessus, en mètres.

        La grille du lidar a 5 cm de côté et part de `origin`. On rend la
        liste des cases occupées : c'est ce que l'application dessine, et
        c'est bien plus léger que le maillage complet.
        """
        mesh = donnees.get("data")
        if not isinstance(mesh, dict):
            self._signaler("la carte n'a pas de maillage")
            return None
        positions = mesh.get("positions")
        origin = donnees.get("origin")
        resolution = donnees.get("resolution")
        if positions is None or origin is None or resolution is None:
            self._signaler(
                f"il manque une donnee (positions={positions is not None}, "
                f"origin={origin is not None}, resolution={resolution is not None})"
            )
            return None
        try:
            valeurs = positions.tolist() if hasattr(positions, "tolist") else list(positions)
            pas = float(resolution)
            x0 = float(origin[0])
            y0 = float(origin[1])
        except (TypeError, ValueError, IndexError) as exc:
            self._signaler(f"la carte est illisible ({exc})")
            return None

        if not valeurs:
            self._signaler("la carte est vide")
            return None

        cases: set[tuple[float, float]] = set()
        for i in range(0, len(valeurs) - 2, 3):
            # Au centime, la carte est plus lisible ; au centieme, elle est
            # deux fois plus legere sur le reseau. Le dessin n'a pas besoin
            # de plus de precision que 10 cm.
            cases.add(
                (
                    round(x0 + valeurs[i] * pas, 1),
                    round(y0 + valeurs[i + 1] * pas, 1),
                )
            )
        return [[x, y] for x, y in cases]

    def _sur_pose(self, message: Any) -> None:
        """La pose du robot dans le repere de la carte du lidar.

        Elle dit ou est le robot SUR LA CARTE, et vers quoi il regarde.
        C'est indispensable : la carte est exprimee dans le repere « odom »
        (celui du monde), pas dans celui du robot — le chien doit donc etre
        pose a cette place, et tourne de ce cap.
        """
        donnees = (message or {}).get("data") or {}
        if not isinstance(donnees, dict):
            return
        pose = donnees.get("pose") or {}
        if not isinstance(pose, dict):
            return
        position = pose.get("position") or {}
        orientation = pose.get("orientation") or {}
        try:
            x = float(position["x"])
            y = float(position["y"])
            qx = float(orientation.get("x", 0.0))
            qy = float(orientation.get("y", 0.0))
            qz = float(orientation.get("z", 0.0))
            qw = float(orientation.get("w", 1.0))
        except (KeyError, TypeError, ValueError):
            return
        # Le cap, autour de l'axe vertical de la carte.
        cap = math.atan2(
            2 * (qw * qz + qx * qy),
            1 - 2 * (qy * qy + qz * qz),
        )
        self._pose_robot = {"x": x, "y": y, "cap": cap}
        self._pose_robot_at = time.monotonic()
        if not self._pose_vue:
            self._pose_vue = True
            log.info(
                "Lidar : pose du robot dans la carte, position (%.3f, %.3f), cap %.1f degres.",
                x,
                y,
                math.degrees(cap),
            )

    def _signaler(self, raison: str) -> None:
        """Explique une fois pourquoi la carte du lidar n'est pas lue."""
        if self._lidar_raison == raison:
            return
        self._lidar_raison = raison
        log.info("Lidar : carte non lue, %s.", raison)

    async def lidar_points(self) -> list[list[float]] | None:
        """Cases occupées de la carte du lidar, vues du dessus, en mètres.

        `None` quand le lidar n'a rien envoyé : on n'invente pas de carte.
        """
        self._derniere_requete_lidar = time.monotonic()
        if not self._lidar_physique_actif and not self._en_veille:
            await self.set_lidar_switch(True)
        if not self._points_lidar:
            return None
        if time.monotonic() - self._points_lidar_at > self.LIDAR_PERIME_S:
            return None
        return self._points_lidar

    async def clearance_m(self, direction: str) -> float | None:
        """Distance libre dans une direction, d'après la carte du lidar.

        `None` tant que la carte ou la pose manque, qu'elles sont trop
        anciennes, ou que la sécurité lidar a été désactivée par un adulte :
        une absence de mesure ne prouve pas que la voie est libre. L'appelant
        décide alors de faire confiance ou non.
        """
        if not self.obstacle_safety_enabled:
            return None
        pose = self._pose_robot
        if self._connexion is None or pose is None or self._obstacles_lidar is None:
            return None
        maintenant = time.monotonic()
        if maintenant - self._pose_robot_at > self.LIDAR_PERIME_S:
            return None
        if maintenant - self._obstacles_lidar_at > self.LIDAR_PERIME_S:
            return None
        return free_distance_m(
            self._obstacles_lidar,
            (float(pose["x"]), float(pose["y"])),
            float(pose["cap"]),
            direction,
        )

    async def _attendre_carte_lidar(self, timeout_s: float = 1.2) -> None:
        """Attend une carte fraîche, sans jamais bloquer indéfiniment.

        Après un relèvement, le lidar met un instant à republier. On attend
        au maximum `timeout_s`. Si aucune carte n'a jamais été reçue, on ne
        perd pas de temps : le lidar n'est probablement pas disponible.
        """
        if self._obstacles_lidar is None:
            return
        fin = time.monotonic() + timeout_s
        while time.monotonic() < fin:
            if time.monotonic() - self._obstacles_lidar_at <= self.LIDAR_PERIME_S:
                return
            await asyncio.sleep(0.05)

    # -- Arret -------------------------------------------------------------

    async def request_stop(self) -> None:
        """Arret immediat, jamais bloquant.

        Ordre retenu : consigne nulle, puis `StopMove`. Les deux envois sont
        sans attente de reponse — un arret qui depend du reseau n'est pas un
        arret.

        ⚠️ EXCEPTION 1 : si le robot est ASSIS ou ALLONGÉ, on n'envoie RIEN.
        Sur un Go2, une commande `Move` releve le robot, et `StopMove` le
        releve aussi : la fin d'un programme termine par « s'asseoir » le
        remettrait debout aussitot, sans que l'ait demande.

        ⚠️ EXCEPTION 2 : si un arrêt de sécurité est actif, on n'envoie RIEN
        non plus. Le déclencheur a déjà envoyé `Move(0)`, `StopMove` puis
        `Damp`. Renvoyer `Move` ici relèverait le robot et annulerait le
        relâchement des pattes.
        """
        # Un arrêt de sécurité reste un état d'erreur tant que le robot n'est
        # pas réarmé : la fin de programme ne doit pas le faire disparaître.
        if not self._securite.latched:
            self._state = RobotState.IDLE
        # Le programme est fini : c'est le moment où le relevage automatique
        # peut agir, si le lidar est bloqué.
        self._programme_en_cours = False
        if self._connexion is None:
            return
        if self._securite.latched:
            return
        if self._est_au_sol():
            # Assis, allongé, ou en train de se poser : le robot ne se
            # déplace pas, il n'y a donc aucune consigne à annuler. Et
            # surtout : une consigne de vitesse le relèverait.
            log.info("Robot au sol : aucune consigne d'arret envoyee.")
            return
        try:
            self._envoyer_move(0.0, 0.0, 0.0)
            self._envoyer_sans_reponse("StopMove")
        except Exception:  # noqa: BLE001
            pass

    # -- Test de connexion -------------------------------------------------

    async def self_test(self, timeout_s: float = 8.0) -> dict[str, object]:
        """Test de connexion : met le robot en position assise.

        `Sit` abaisse le robot vers un etat stable et prouve que le canal
        d'ALLER est accepte, pas seulement la reception d'etat.
        """
        rapport: dict[str, object] = {
            "robot_ip": self._robot_ip,
            "interface": "webrtc",
            "connecte": self._connected,
            "commande_envoyee": None,
            "succes": False,
            "message": "",
        }

        if not self._connected or self._connexion is None:
            rapport["message"] = "Le robot n’est pas connecté."
            return rapport

        # La descente en position assise décharge les pieds avant que le code
        # d'état ne passe à 1007 : ce n'est pas un portage.
        self._posture_grace_until = time.monotonic() + self.POSTURE_GRACE_S
        try:
            code = await self._commander("Sit", timeout_s=self.POSTURE_TIMEOUT_S)
        except AdapterError as exc:
            rapport["message"] = str(exc)
            return rapport

        if code is None:
            rapport["message"] = (
                "Le robot n’a pas répondu à la commande « s’asseoir »."
            )
            return rapport
        if code != 0:
            # Le robot refuse « s'asseoir » s'il l'est DÉJÀ : ce n'est pas
            # un défaut de liaison, c'est la bonne réponse. Le canal d'aller
            # est alors prouvé par l'état qu'il publie.
            if self._code_etat == self.ETAT_ASSIS_CODE:
                rapport["commande_envoyee"] = "Sit"
                rapport["succes"] = True
                self._posture = Posture.SIT
                rapport["message"] = (
                    "Le robot est déjà assis et refuse de se rasseoir : "
                    "le canal d’envoi fonctionne."
                )
                rapport["attente_s"] = 0.0
                return rapport
            rapport["message"] = f"Commande refusée par le robot (code {code})."
            return rapport

        rapport["commande_envoyee"] = "Sit"
        rapport["succes"] = True
        self._posture = Posture.SIT
        rapport["message"] = (
            "Commande « s’asseoir » acquittée par le robot. "
            "Le canal d’envoi fonctionne."
        )

        attente = min(timeout_s, 2.0)
        await asyncio.sleep(attente)
        rapport["attente_s"] = round(attente, 1)
        return rapport
