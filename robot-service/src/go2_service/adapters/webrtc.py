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
from typing import Any

from ..config import Limits
from ..validation import Capability, CommandKind, RobotCommand
from .base import (
    AdapterError,
    CommandOutcome,
    MotionPlan,
    Posture,
    RobotState,
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

    #: Au-dela de ce silence, l'etat est declare perdu.
    STATE_STALE_S = 2.0

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

    #: Code d'etat publie quand le robot est ASSIS.
    ETAT_ASSIS = 1007

    #: Attente maximale du retour a l'etat "pret".
    PRET_TIMEOUT_S = 12.0

    #: Periode minimum entre deux images encodees (secondes).
    #: 5 images par seconde suffisent a une vue d'enfant, et cela evite
    #: de saturer le processeur du service.
    CAMERA_PERIODE_S = 0.2

    #: Au-dela de cette anciennete, la carte du lidar est consideree
    #: comme perimee : mieux vaut une vue vide qu'une carte trompeuse.
    LIDAR_PERIME_S = 2.0

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

        self._connexion: Any = None
        self._rtc: Any = None
        self._sport_cmd: Any = None
        self._types_canal: Any = None

        self._connected = False
        self._state = RobotState.UNKNOWN
        self._posture: Posture | None = None

        self._position: tuple[float, float, float] | None = None
        self._yaw: float | None = None
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
        self._velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._mode: int | None = None
        self._last_state_at: float | None = None
        #: Code d'etat publie par le robot (100 = pret, 1002 = transition).
        self._code_etat: int | None = None
        #: Plus haute hauteur vue depuis la connexion : sert de reference
        #: pour savoir si le robot est actuellement assis.
        self._hauteur_max: float | None = None
        #: Derniere image de la camera du robot, en JPEG.
        self._dernier_jpeg: bytes | None = None
        self._dernier_jpeg_at: float = 0.0
        self._tache_video: asyncio.Task[None] | None = None
        #: Derniere carte du lidar recue.
        self._points_lidar: list[list[float]] | None = None
        self._points_lidar_at: float = 0.0
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
        #: Le robot marche-t-il tout seul ?
        self._autonome = False

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
        self._sport_cmd = SPORT_CMD
        self._types_canal = DATA_CHANNEL_TYPE
        self._premier_etat = asyncio.Event()
        # Le cap cumulé repart de zéro à chaque connexion : une valeur gardée
        # d'une session précédente ne décrit plus le robot.
        self._cap_cumule = None
        self._yaw_precedent = None
        self._cap_mesure_at = None

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

        # La camera du robot, si elle existe : c'est une degradee, pas une
        # condition de pilotage.
        await self._demarrer_video()

        # Le lidar : de meme, sa vue est un bonus, pas une condition.
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
        self._cap_cumule = None
        self._yaw_precedent = None
        self._cap_mesure_at = None
        self._state = RobotState.DISCONNECTED

    # -- Reception de l'etat ----------------------------------------------

    def _sur_etat(self, message: Any) -> None:
        """Memorise l'etat publie par le robot. Ne doit jamais lever."""
        donnees = (message or {}).get("data") or {}
        try:
            # L'etat du robot est lu EN PREMIER : la hauteur de reference
            # doit etre jugee avec le code du MEME message.
            code_etat = donnees.get("error_code")
            if isinstance(code_etat, (int, float)):
                self._code_etat = int(code_etat)

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
                yaw = float(rpy[2])
                maintenant = time.monotonic()
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

            self._last_state_at = time.monotonic()
        except (TypeError, ValueError, AttributeError):
            # Un etat illisible vaut « inconnu », jamais une valeur inventee.
            pass

        if self._premier_etat is not None:
            self._premier_etat.set()

    def _sur_batterie(self, message: Any) -> None:
        """Lit le niveau de batterie s'il est present, sinon ne touche a rien."""
        donnees = (message or {}).get("data") or {}
        candidats: list[Any] = []
        bms = donnees.get("bms_state")
        if isinstance(bms, dict):
            candidats.append(bms.get("soc"))
        candidats.append(donnees.get("soc"))
        for valeur in candidats:
            if isinstance(valeur, (int, float)):
                self._battery = float(valeur)
                return

    # -- Etat --------------------------------------------------------------

    async def get_status(self) -> Status:
        """Etat connu. Ne leve jamais."""
        if not self._connected:
            return Status(
                connected=False,
                state=RobotState.DISCONNECTED,
                capabilities=UNITREE_CAPABILITIES,
                blocked_reason="Le service n’est pas connecté au robot.",
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
        )

    # -- Emission ----------------------------------------------------------

    def _enveloppe(self, nom: str, parametre: Any = "") -> dict[str, Any]:
        """Construit le message attendu par le canal, sans attendre de reponse."""
        identifiant = int(time.time() * 1000) % 2147483648 + random.randint(0, 1000)
        return {
            "header": {
                "identity": {"id": identifiant, "api_id": self._sport_cmd[nom]}
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

    async def _commander(self, nom: str, parametre: Any = "") -> int | None:
        """Envoie une commande et attend son acquittement.

        Retourne le code de statut renvoye par le robot, ou `None` si le
        robot n'a pas repondu dans le delai.
        """
        connexion = self._connexion
        if connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        log.info("Commande envoyee au robot : %s", nom)
        demande = {"api_id": self._sport_cmd[nom]}
        if parametre != "":
            demande["parameter"] = parametre

        try:
            reponse = await asyncio.wait_for(
                connexion.datachannel.pub_sub.publish_request_new(
                    self._rtc["SPORT_MOD"], demande
                ),
                timeout=self.COMMAND_TIMEOUT_S,
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
        if self._est_debout():
            # Déjà sur ses pattes : rien à demander.
            return
        log.info(
            "Robot non debout (posture %s, etat %s) : remise sur quatre pattes.",
            self._posture,
            self._code_etat,
        )
        await self._relever()

    # -- Execution ---------------------------------------------------------

    async def execute_command(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        if not self.physical_commands_enabled:
            raise AdapterError(
                "L’adaptateur WebRTC n’est pas activé : commande refusée."
            )
        if not self._connected or self._connexion is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        match command.kind:
            case CommandKind.WAIT:
                return await self._do_wait(command.seconds, index, should_stop)
            case CommandKind.STAND_UP:
                return await self._do_posture("StandUp", Posture.STAND, index)
            case CommandKind.SIT_DOWN:
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
                # `FrontPounce` : la commande SDK qui donne la vraie
                # impulsion (`FrontJump` ne fait qu'accroupir et pousser).
                #
                # Le geste n'est exécuté que si l'on parle au robot en
                # vitesse pendant ce temps (voir `_flux_vitesse`), comme
                # le fait l'application mobile.
                return await self._do_geste("FrontPounce", index)
            case CommandKind.LIE_DOWN:
                # `Damp` : le robot s'allonge (il ne se déplace plus).
                # Pas de flux de vitesse : on veut qu'il se pose.
                return await self._do_geste(
                    "Damp",
                    index,
                    lever_si_assis=False,
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
            if should_stop.requested:
                return CommandOutcome(index=index, outcome="stopped")
            await asyncio.sleep(min(0.05, restant))
            restant -= 0.05
        return CommandOutcome(index=index, outcome="exact")

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
        for essai in range(2):
            code = await self._commander(nom)
            if code is None:
                # Pas de reponse : on ne peut rien affirmer.
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

            if posture is Posture.STAND:
                # Reprendre la main sur la vitesse : c'est la consigne NULLE
                # qui fait sortir le robot de sa transition. On attend ensuite
                # l'état « pret » : c'est lui, et lui seul, qui dit que le
                # robot est vraiment debout.
                self._prendre_la_main()
                if not await self._attendre_pret():
                    log.info("Le robot ne signale pas son retour a l'etat pret.")

            if not self._posture_tenue(posture):
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

        flux: asyncio.Task[None] | None = None
        if flux_vitesse:
            flux = asyncio.create_task(self._flux_vitesse(4.0))
            # Le temps que le robot passe en « en mouvement ».
            await asyncio.sleep(0.8)

        try:
            code = await self._commander(nom)
        except AdapterError as exc:
            raise AdapterError(f"Le robot n’a pas acquitté le geste : {exc}") from exc
        finally:
            if flux is not None:
                flux.cancel()

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

        debut: float | None = None
        dernier_envoi = 0.0
        resultat = "exact"
        motif: str | None = None
        try:
            while True:
                if should_stop is not None and should_stop.requested:
                    resultat = "stopped"
                    break

                maintenant = time.monotonic()
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
        try:
            while True:
                if should_stop is not None and should_stop.requested:
                    resultat = "stopped"
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
                if abs(ecart) <= YAW_BANDE_MORTE_DEG:
                    break

                if (
                    dernier_envoi == 0.0
                    or maintenant - dernier_envoi >= self.MOVE_REFRESH_S
                ):
                    vitesse = yaw_rate_for_remaining(abs(ecart), vitesse_max)
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
        """
        return self._dernier_jpeg

    async def _demarrer_video(self) -> None:
        """Demande la camera du robot et garde la derniere image.

        Le SDK expose un canal video (`conn.video`) : on s'y abonne, et on
        garde la derniere image recue, encodee en JPEG.
        """
        connexion = self._connexion
        if connexion is None:
            return
        try:
            video = connexion.video
            video.add_track_callback(self._lire_video)
            video.switchVideoChannel(True)
            log.info("Camera du robot demandee.")
        except Exception as exc:  # noqa: BLE001
            # Pas de camera n'est une degradee, pas une panne : le service
            # continue a piloter le robot.
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

    # -- Mode autonome -----------------------------------------------------

    async def set_autonome(self, actif: bool) -> bool:
        """Active ou coupe la marche autonome du robot.

        Deux commandes officielles du SDK :
        - l'évitement d'obstacles (`rt/api/obstacles_avoid/request`,
          `SWITCH_SET`) : c'est lui qui allume le lidar ;
        - la marche libre (`FreeWalk`), que le robot exécute tout seul.

        Couper le mode s'arrête d'abord le robot, puis éteint l'évitement.
        """
        connexion = self._connexion
        if connexion is None:
            return False

        if not actif:
            await self.request_stop()
            self._autonome = False
            self._publier_avoid(False)
            return True

        self._publier_avoid(True)
        try:
            code = await self._commander("FreeWalk")
        except AdapterError as exc:
            log.warning("Marche autonome refusee : %s", exc)
            self._publier_avoid(False)
            return False
        if code is None:
            log.warning("Marche autonome : le robot n'a pas repondu.")
            self._publier_avoid(False)
            return False
        if code != 0:
            # 3203 : le robot refuse dans l'espace de commandes normal.
            # La marche libre de l'application passe par l'espace MCF, qui
            # exige au prealable la bascule de mode (`motion_switcher`).
            log.warning("Marche autonome refusee par le robot (code %s).", code)
            self._publier_avoid(False)
            return False
        self._autonome = True
        return True

    def _publier_avoid(self, actif: bool) -> None:
        """Allume (ou éteint) l'évitement d'obstacles du robot."""
        connexion = self._connexion
        if connexion is None:
            return
        sujet = self._rtc.get(
            "OBSTACLES_AVOID", "rt/api/obstacles_avoid/request"
        )
        try:
            connexion.datachannel.pub_sub.publish_without_callback(
                topic=sujet,
                data={"api_id": 1001, "parameter": {"enable": actif}},
            )
            log.info("Evitement d'obstacles : %s", "actif" if actif else "coupe")
        except Exception as exc:  # noqa: BLE001
            log.info("Evitement d'obstacles indisponible : %s", exc)

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
            canal.subscribe(self._rtc["ULIDAR_ARRAY"], self._sur_lidar)
            canal.subscribe(self._rtc["ULIDAR"], self._sur_lidar)
            canal.subscribe(self._rtc["ULIDAR_STATE"], self._sur_lidar)
            # La pose du robot DANS le repere du lidar : c'est elle qui dit
            # ou est le robot sur la carte, et dans quel sens il regarde.
            canal.subscribe(self._rtc["ROBOTODOM"], self._sur_pose)
            # On demande l'allumage. Le SDK ne le fait pas tout seul : c'est
            # ce que fait l'application quand on ouvre la vue capteur.
            for charge in ({"enable": True}, "on", {"switch": "on"}):
                try:
                    canal.publish_without_callback(
                        topic=self._rtc["ULIDAR_SWITCH"], data=charge
                    )
                except Exception:  # noqa: BLE001
                    break
                await asyncio.sleep(1.0)
            log.info("Lidar demande.")
        except Exception as exc:  # noqa: BLE001
            log.info("Lidar indisponible : %s", exc)

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
        if not self._points_lidar:
            return None
        if time.monotonic() - self._points_lidar_at > self.LIDAR_PERIME_S:
            return None
        return self._points_lidar

    # -- Arret -------------------------------------------------------------

    async def request_stop(self) -> None:
        """Arret immediat, jamais bloquant.

        Ordre retenu : consigne nulle, puis `StopMove`. Les deux envois sont
        sans attente de reponse — un arret qui depend du reseau n'est pas un
        arret.

        ⚠️ EXCEPTION : si le robot est ASSIS, on n'envoie RIEN.

        Sur un Go2, une commande `Move` releve le robot, et `StopMove` le
        releve aussi : la fin d'un programme termine par « s'asseoir » le
        remettrait debout aussitot, sans que l'ait demande. Un robot assis
        ne se deplace pas : il n'y a donc aucune consigne de mouvement a
        annuler, et le silence est la seule reponse honnete.
        """
        self._state = RobotState.IDLE
        if self._connexion is None:
            return
        if self._est_assis() or self._est_alleonge():
            # Assis ou allongé : le robot ne se déplace pas, il n'y a donc
            # aucune consigne à annuler. Et surtout : une consigne de vitesse
            # le relèverait.
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

        try:
            code = await self._commander("Sit")
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
