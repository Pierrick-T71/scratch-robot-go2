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
import json
import logging
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
    POSITION_TOLERANCE_CM,
    YAW_TOLERANCE_DEG,
    assert_speed_within_limits,
    plan_command,
    shortest_angular_difference_deg,
    travelled_distance_cm,
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

    #: Code d'etat publie par le robot quand il est PRET a marcher.
    #: Mesure sur la machine : 100 = debout, au repos ou en marche.
    ETAT_PRET = 100

    #: Code d'etat publie pendant une TRANSITION de posture. Le robot
    #: ignore alors les consignes de mouvement — et les lui envoyer
    #: l'empeche meme de finir sa transition.
    ETAT_TRANSITION = 1002

    #: Code d'etat publie quand le robot est ASSIS.
    ETAT_ASSIS = 1007

    #: Attente maximale du retour a l'etat "pret".
    PRET_TIMEOUT_S = 12.0

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
        self._battery: float | None = None
        self._velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._mode: int | None = None
        self._last_state_at: float | None = None
        #: Code d'etat publie par le robot (100 = pret, 1002 = transition).
        self._code_etat: int | None = None
        #: Plus haute hauteur vue depuis la connexion : sert de reference
        #: pour savoir si le robot est actuellement assis.
        self._hauteur_max: float | None = None

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

    async def disconnect(self) -> None:
        """Immobilise le robot, puis ferme le canal."""
        try:
            await self.request_stop()
        except Exception:  # noqa: BLE001 - on veut fermer quand meme
            pass

        connexion = self._connexion
        if connexion is not None:
            try:
                connexion.datachannel.switchAudioChannel(False)
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
        self._state = RobotState.DISCONNECTED

    # -- Reception de l'etat ----------------------------------------------

    def _sur_etat(self, message: Any) -> None:
        """Memorise l'etat publie par le robot. Ne doit jamais lever."""
        donnees = (message or {}).get("data") or {}
        try:
            position = donnees.get("position") or []
            if len(position) >= 3:
                self._position = (
                    float(position[0]),
                    float(position[1]),
                    float(position[2]),
                )
                # Reference de la hauteur debout : le robot assis est plus bas.
                hauteur = float(position[2])
                if self._hauteur_max is None or hauteur > self._hauteur_max:
                    self._hauteur_max = hauteur

            imu = donnees.get("imu_state") or {}
            rpy = imu.get("rpy") or []
            if len(rpy) >= 3:
                self._yaw = float(rpy[2])

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

            code_etat = donnees.get("error_code")
            if isinstance(code_etat, (int, float)):
                self._code_etat = int(code_etat)

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

    def _est_assis(self) -> bool:
        """Le robot est-il assis ?

        Trois sources, dans cet ordre :

        1. le CODE D'ETAT publie par le robot (`1007` = assis) ;
        2. la MESURE : la hauteur lue dans l'état du robot. Un Go2 debout
           fait ~0,32 m, assis ~0,22 m. On compare à la plus haute hauteur
           vue depuis la connexion ;
        3. notre DERNIER ordre de posture, quand la mesure manque.

        On ne suppose jamais « debout » : une posture qu'on ne peut pas
        vérifier est traitée comme « à remettre debout ».
        """
        if self._code_etat == self.ETAT_ASSIS:
            return True
        hauteur = self._position[2] if self._position else None
        reference = self._hauteur_max
        if hauteur is not None and reference is not None:
            return hauteur < reference * self.SITUE_RATIO
        if self._posture is Posture.SIT:
            return True
        return self._posture is None

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
            if code == self.ETAT_PRET:
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
        if not self._est_assis():
            # Déjà sur ses pattes : rien à demander.
            return
        log.info(
            "Robot non debout (posture %s, hauteur %s) : remise sur quatre pattes.",
            self._posture,
            self._position[2] if self._position else None,
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

        Le SDK ne publie pas la posture : on la déduit de la HAUTEUR lue dans
        l'état. Un Go2 debout fait ~0,32 m, assis ~0,22 m.

        Sans mesure, on ne peut pas trancher : on ne retire jamais au robot
        une posture qu'il a acquittée.
        """
        hauteur = self._position[2] if self._position else None
        reference = self._hauteur_max
        if hauteur is None or reference is None:
            return True
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

            if not self._posture_tenue(posture):
                log.info(
                    "Le robot n'a pas tenu la posture %s : on recommence.",
                    posture.value,
                )
                continue

            if posture is Posture.STAND:
                self._prendre_la_main()
                if not await self._attendre_pret():
                    log.info("Le robot ne signale pas son retour a l'etat pret.")

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

    async def _do_posture(
        self, nom: str, posture: Posture, index: int
    ) -> CommandOutcome:
        resultat = await self._appliquer_posture(nom, posture)
        return CommandOutcome(
            index=index,
            outcome=resultat.outcome,
            detail=resultat.detail,
        )

    async def _do_move(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        plan = plan_command(command, self._limits)
        if plan is None:
            raise AdapterError(f"Commande non gérée : {command.kind.value}")

        # Un déplacement suppose le robot debout. Le SDK le relèverait de
        # lui-même ; on le fait explicite, pour ne pas laisser le mouvement
        # dépendre d'un effet de bord.
        if self._posture == Posture.SIT:
            await self._relever()

        # Le robot n'accepte les consignes de mouvement que dans l'état
        # « prêt ». Pendant une transition de posture, il les IGNORE — et
        # les lui envoyer empêche même la transition de se terminer. On
        # attend donc, on n'envoie rien.
        if self._code_etat is not None and self._code_etat != self.ETAT_PRET:
            if self._code_etat == self.ETAT_ASSIS:
                await self._relever()
            else:
                log.info(
                    "Robot en etat %s : on attend qu'il soit pret a bouger.",
                    self._code_etat,
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

        # Dernier point de controle avant que la valeur n'atteigne le canal.
        assert_speed_within_limits(plan, self._limits)

        depart = await self.get_status()
        depart_xy = (
            (depart.position_m[0], depart.position_m[1])
            if depart.position_m
            else None
        )
        depart_yaw = depart.yaw_rad

        log.info(
            "Deplacement %s : vitesse %.2f m/s, duree nominale %.1f s, delai d'arret %.1f s",
            command.kind.value,
            plan.linear_speed_mps,
            plan.nominal_duration_s,
            plan.timeout_s,
        )

        self._state = RobotState.MOVING
        boucle = asyncio.get_running_loop()
        dernier_envoi = 0.0
        ecoule = 0.0
        pas = 0.05

        try:
            while True:
                if should_stop.requested:
                    await self.request_stop()
                    return CommandOutcome(index=index, outcome="stopped")

                maintenant = boucle.time()
                if maintenant - dernier_envoi >= self.MOVE_REFRESH_S:
                    if dernier_envoi == 0.0:
                        log.info(
                            " Premiere consigne Move : x=%.2f y=%.2f z=%.2f m/s",
                            plan.linear_speed_mps,
                            plan.lateral_speed_mps,
                            plan.angular_speed_rps,
                        )
                    self._envoyer_move(
                        plan.linear_speed_mps,
                        plan.lateral_speed_mps,
                        plan.angular_speed_rps,
                    )
                    dernier_envoi = maintenant

                await asyncio.sleep(pas)
                ecoule += pas

                etat = await self.get_status()
                if not etat.connected or etat.blocked_reason:
                    raise AdapterError(
                        "Liaison perdue pendant le déplacement.", recoverable=True
                    )

                if self._arrive(plan, depart_xy, depart_yaw, etat):
                    await self.request_stop()
                    return self._bilan(
                        index, plan, depart_xy, depart_yaw, etat, "exact"
                    )

                if ecoule >= plan.timeout_s:
                    await self.request_stop()
                    return self._bilan(
                        index, plan, depart_xy, depart_yaw, etat, "timeout"
                    )
        finally:
            # Toute sortie, y compris une exception, repasse par l'arret.
            await self.request_stop()

    def _arrive(
        self,
        plan: MotionPlan,
        depart_xy: tuple[float, float] | None,
        depart_yaw: float | None,
        etat: Status,
    ) -> bool:
        """Compare la consigne a l'ETAT MESURE, jamais a la duree ecoulee."""
        if plan.distance_cm > 0:
            if depart_xy is None or etat.position_m is None:
                return False
            parcouru = travelled_distance_cm(
                depart_xy, (etat.position_m[0], etat.position_m[1])
            )
            return parcouru >= plan.distance_cm - POSITION_TOLERANCE_CM

        if plan.angle_deg > 0:
            if depart_yaw is None or etat.yaw_rad is None:
                return False
            parcouru = shortest_angular_difference_deg(depart_yaw, etat.yaw_rad)
            return parcouru >= plan.angle_deg - YAW_TOLERANCE_DEG

        return False

    def _bilan(
        self,
        index: int,
        plan: MotionPlan,
        depart_xy: tuple[float, float] | None,
        depart_yaw: float | None,
        etat: Status,
        resultat: str,
    ) -> CommandOutcome:
        """Resultat construit sur la mesure, jamais sur la consigne."""
        if plan.distance_cm > 0 and depart_xy and etat.position_m:
            mesure = travelled_distance_cm(
                depart_xy, (etat.position_m[0], etat.position_m[1])
            )
            return CommandOutcome(
                index=index, outcome=resultat, measured_distance_cm=round(mesure, 1)
            )
        if plan.angle_deg > 0 and depart_yaw is not None and etat.yaw_rad is not None:
            mesure = shortest_angular_difference_deg(depart_yaw, etat.yaw_rad)
            return CommandOutcome(
                index=index, outcome=resultat, measured_angle_deg=round(mesure, 1)
            )
        return CommandOutcome(
            index=index,
            outcome=resultat,
            detail="Aucune mesure disponible pour cette instruction.",
        )

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
        if self._est_assis():
            log.info("Robot assis : aucune consigne d'arret envoyee.")
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
