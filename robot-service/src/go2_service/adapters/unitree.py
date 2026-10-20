"""Adaptateur Unitree Go2 — intégration physique NON VALIDÉE.

============================================================
ÉTAT : À VÉRIFIER. Ce code n'a JAMAIS été exécuté sur un robot.
============================================================

Ce fichier implémente uniquement des méthodes dont l'existence a été lue
dans le code officiel du SDK, et n'invente aucun identifiant :

  Source : https://github.com/unitreerobotics/unitree_sdk2
           example/go2/go2_sport_client.cpp
           example/go2/go2_robot_state_client.cpp
  Source : https://github.com/unitreerobotics/unitree_sdk2_python
           example/go2/high_level/go2_sport_client.py

API réellement vérifiée dans ces fichiers
------------------------------------------
  from unitree_sdk2py.core.channel import ChannelFactoryInitialize
  from unitree_sdk2py.go2.sport.sport_client import SportClient

  ChannelFactoryInitialize(0, <interface_réseau>)
  client = SportClient(); client.SetTimeout(10.0); client.Init()
  client.Move(vx, vy, vyaw)   -> retourne un code d'erreur
  client.StopMove()
  client.StandUp(); client.StandDown(); client.Damp()
  client.BalanceStand(); client.RecoveryStand()

  État mesuré : sujet DDS "rt/sportmodestate", type SportModeState_
  avec .position() et .imu_state().rpy()

RISQUE PRINCIPAL DOCUMENTÉ
--------------------------
`Move()` définit une CONSIGNE DE VITESSE PERSISTANTE. L'exemple officiel ne
fait jamais de `StopMove()` en sortie de boucle. Si ce processus s'arrête, si
le réseau tombe ou si le watchdog n'est pas arme, LE ROBOT PEUT CONTINUER DE
MARCHER AVEC SA DERNIERE VITESSE.

C'est la raison d'être du chien de garde (`safety.py`) et du bail : le service
doit rester propriétaire du cycle de vie, jamais l'interface.

À VÉRIFIER AVANT TOUT PILOTAGE RÉEL
------------------------------------
  1. Modèle exact (Go2 Pro ?), version matérielle, firmware, options.
  2. Version installée de `unitree_sdk2_python` et signature réelle de
     `SportClient.Move` (les 3 arguments, l'ordre vx/vy/vyaw).
  3. Existence de `Sit()` et `RiseSit()` côté Python : présents dans
     l'exemple C++, ABSENTS de la liste de l'exemple Python.
  4. Comportement RÉEL de `StopMove()` : immobilisation immédiate ou
     amortissement progressif ? Délai avant arrêt ?
  5. Comportement de `Damp()` : est-ce l'arrêt le plus sûr disponible ?
  6. Signification EXACTE du code d'erreur retourné par `Move()`.
  7. Validité de `SportModeState.position()` comme retour de position
     (position estimée, pas une odométrie : dérive possible).
  8. Fréquence de publication requise (l'exemple utilise dt = 0.005 s).
  9. Interface réseau correcte et commande `ifconfig` correspondante.

Aucune commande basse niveau n'est implémentée : ni `rt/lowcmd`, ni CRC32,
ni pilotage moteur. Hors périmètre pédagogique.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
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

log = logging.getLogger(__name__)

#: Capacités réellement vérifiées dans les exemples officiels.
#:
#: `SENSOR_STATE` est incluse : le sujet `rt/sportmodestate` et le type
#: `SportModeState_` ont été lus dans l'exemple officiel.
#:
#: `SENSOR_OBSTACLE` est EXCLUE, volontairement : aucune mesure de distance
#: d'obstacle n'a été identifiée dans l'API officielle. Sans cette absence,
#: un bloc capteur afficherait un nombre fabriqué sur un vrai robot.
#:
#: `VARIABLE` et `BROADCAST` sont incluses sans réserve : ces actions ne
#: commandent aucun organe, elles s'exécutent dans le service.
UNITREE_CAPABILITIES = frozenset(
    {
        Capability.MOVEMENT,
        Capability.POSTURE,
        Capability.WAIT,
        Capability.STOP,
        Capability.VARIABLE,
        Capability.BROADCAST,
        Capability.SENSOR_STATE,
    }
)

#: Sujet DDS de l'état du robot. Constante TOPIC_HIGHSTATE dans l'exemple C++.
TOPIC_HIGHSTATE = "rt/sportmodestate"


class UnitreeValidationError(RuntimeError):
    """Le SDK n'est pas disponible ou pas validé sur cette machine."""


class UnitreeAdapter:
    """Adaptateur physique. DÉSACTIVÉ tant que la validation n'a pas eu lieu.

    `physical_commands_enabled` vaut `False` : tant qu'il en est ainsi, le
    service refuse de passer en mode réel, quel que soit le client.
    Passer cette valeur à `True` est un acte délibéré, documenté, qui ne doit
    être fait qu'après la procédure de `docs/ROBOT_SETUP.md`.
    """

    name = "unitree"

    #: Verrou de la CLASSE : un adaptateur fraichement construit refuse
    #: toute commande. L'activation passe par `enable_physical_commands()`,
    #: qui agit sur l'INSTANCE — jamais sur la classe. Un seul test malencontreux
    #: ne peut donc pas ouvrir le pilotage a tout le service.
    physical_commands_enabled = False

    def __init__(
        self,
        limits: Limits,
        network_interface: str,
        robot_ip: str | None = None,
    ) -> None:
        self._limits = limits
        self._interface = network_interface
        #: Adresse du robot. Le DDS travaille en multicast et ne s'adresse
        #: donc PAS au robot par IP : cette valeur sert au controle de
        #: joignabilite, et a l'affichage pour que l'utilisateur sache quel
        #: robot il pilote.
        self._robot_ip = robot_ip
        #: Verrou d'instance, sur la classe.
        self.physical_commands_enabled = False

        self._client: Any = None
        self._connected = False
        self._state = RobotState.UNKNOWN
        self._posture = Posture.SIT

        self._lock = threading.Lock()
        self._setpoint = (0.0, 0.0, 0.0)
        self._position: tuple[float, float, float] | None = None
        self._yaw: float | None = None
        self._battery: float | None = None

        self._publish_thread: threading.Thread | None = None
        self._publish_running = False
        self._last_publish_ok = False
        self._shutdown = threading.Event()
        #: Dernier état reçu via `rt/sportmodestate`, s'il y en a un.
        self._last_state: Any = None
        #: Abonné d'état, et preuve qu'il a déjà reçu quelque chose.
        self._state_channel: Any = None
        self._last_state_ok = False

    # -- Journalisation des inconnues -------------------------------------

    #: Éléments non vérifiés, à trancher lors de la campagne physique.
    UNVERIFIED = (
        "Signature exacte de SportClient.Move en Python.",
        "Disponibilité de Sit() / RiseSit() côté Python.",
        "Immobilisation réelle après StopMove() et délai associé.",
        "Sécurité comparative de Damp() comme arrêt.",
        "Code d'erreur retourné par Move().",
        "Fiabilité de SportModeState.position() comme retour mesuré.",
        "Fréquence minimale de publication acceptée par le contrôleur.",
    )

    # -- Cycle de vie ------------------------------------------------------

    @property
    def robot_ip(self) -> str | None:
        return self._robot_ip

    @property
    def network_interface(self) -> str:
        return self._interface

    def enable_physical_commands(self) -> None:
        """Ouvre le pilotage physique pour CETTE instance.

        Acte délibéré, jamais appelé implicitement. Le service ne l'appelle
        qu'après un test de connexion réussi.

        ⚠️ Une fois activé, toute commande reçue part vers le robot. C'est
        pourquoi l'activation est attachée à l'instance : un adaptateur créé
        ailleurs dans le service reste verrouillé.
        """
        self.physical_commands_enabled = True

    async def self_test(self, timeout_s: float = 8.0) -> dict[str, object]:
        """Test de connexion : met le robot en position assise.

        CHOIX DE LA POSTURE : `Sit()` est la commande la plus sûre pour une
        première prise de contact. Elle abaisse le robot et le ramène à un
        état stable : un robot debout qui tombe fait mal, un robot assis non.
        Elle prouve en outre que le canal d'ALLER est accepte, pas seulement
        le canal d'etat.

        Renvoie un rapport exploitable par l'interface. Ne leve pas : un
        echec doit etre RAPPORTE, pas transformer en 500 opaque.
        """
        rapport: dict[str, object] = {
            "robot_ip": self._robot_ip,
            "interface": self._interface,
            "connecte": self._connected,
            "commande_envoyee": None,
            "succes": False,
            "message": "",
        }

        if not self._connected or self._client is None:
            rapport["message"] = "Le robot n’est pas connecté."
            return rapport

        try:
            # `Sit` existe bien cote Python : verifie par introspection du SDK
            # installe (voir docs/ROBOT_SETUP.md §12).
            self._client.Sit()
            rapport["commande_envoyee"] = "Sit"
            rapport["succes"] = True
            self._posture = Posture.SIT
            rapport["message"] = (
                "Commande « s’asseoir » acceptée. "
                "Le robot a bien reçu l’ordre — reste à le voir bouger."
            )
        except Exception as exc:
            rapport["message"] = f"Commande refusée par le robot ({exc})."
            return rapport

        # Attente courte : on laisse le temps au contrôleur de traiter, sans
        # prétendre mesurer quoi que ce soit. On ne dit PAS « il s'est assis ».
        await asyncio.sleep(min(timeout_s, 2.0))
        rapport["attente_s"] = round(min(timeout_s, 2.0), 1)
        return rapport

    async def connect(self) -> None:
        """Ouvre la liaison DDS. Refuse de s'importer sur un poste non compatible."""
        if not self.physical_commands_enabled:
            raise UnitreeValidationError(
                "L’adaptateur Unitree n’est pas validé. "
                "Reste en simulation tant que la campagne physique n’a pas eu lieu."
            )

        try:
            from unitree_sdk2py.core.channel import (  # type: ignore[import-not-found]
                ChannelFactoryInitialize,
            )
            from unitree_sdk2py.go2.sport.sport_client import (  # type: ignore[import-not-found]
                SportClient,
            )
        except ImportError as exc:
            raise UnitreeValidationError(
                "Le SDK Unitree Python n’est pas installé sur cette machine. "
                "Voir docs/ROBOT_SETUP.md."
            ) from exc

        try:
            # L'interface réseau est obligatoire : le robot est joignable
            # uniquement via une interface précise (typiquement eth0).
            ChannelFactoryInitialize(0, self._interface)
            client = SportClient()
            client.SetTimeout(10.0)
            client.Init()
        except Exception as exc:  # le SDK peut lever des erreurs C++ arbitraires
            raise AdapterError(
                f"Connexion au robot impossible ({exc}).", recoverable=True
            ) from exc

        self._client = client
        self._connected = True
        self._state = RobotState.IDLE

        # Ouverture du canal d'ECOUTE.
        #
        # ⚠️ CETTE ETAPE EST LA SEULE VRAIE PREUVE DE CONNEXION.
        #
        # `ChannelFactoryInitialize` et `SportClient.Init()` réussissent
        # localement, sur cette machine, même SANS ROBOT : rien n'attend de
        # réponse. Un service qui se contenterait de leur succès annoncerait
        # « connecté » devant un robot absent — le pire des échecs, puisque
        # l'enfant croirait commander une machine.
        #
        # On ouvre donc un abonné sur `rt/sportmodestate` et on attend
        # réellement qu'un message arrive. Aucun message = pas de robot.
        self._start_state_listener()

    # -- Écoute de l'état --------------------------------------------------

    #: Délai d'attente d'un premier message avant de conclure à l'absence
    #: de robot. Court : c'est un test de joignabilité, pas une connexion.
    STATE_HANDSHAKE_TIMEOUT_S = 4.0

    def _start_state_listener(self) -> None:
        """
        Ouvre un abonné sur l'état du robot et attend sa première publication.

        Lève `AdapterError` si rien n'arrive dans le délai : c'est le seul
        mécanisme qui distingue « robot présent » de « robot absent ».
        """
        try:
            from unitree_sdk2py.core.channel import (  # type: ignore[import-not-found]
                ChannelFactory,
            )
            from unitree_sdk2py.idl.unitree_go.msg.dds_._SportModeState_ import (  # type: ignore[import-not-found]
                SportModeState_,
            )
        except ImportError as exc:
            # Pas de type d'état dans cette version du SDK : on ne peut pas
            # prouver la présence du robot, donc on refuse plutôt que de
            # deviner.
            raise AdapterError(
                "Le type SportModeState_ est absent du SDK installé : "
                "impossible de vérifier que le robot répond.",
                recoverable=True,
            ) from exc

        recu = threading.Event()

        def _handler(message: Any) -> None:
            self._last_state = message
            self._battery = self._read_battery(message)
            self._yaw = self._read_yaw(message)
            self._position = self._read_position(message)
            recu.set()

        factory = ChannelFactory()
        self._state_channel = factory.CreateRecvChannel(
            TOPIC_HIGHSTATE, SportModeState_, _handler, queueLen=8
        )

        if not recu.wait(timeout=self.STATE_HANDSHAKE_TIMEOUT_S):
            raise AdapterError(
                f"Aucun message sur « {TOPIC_HIGHSTATE} » après "
                f"{self.STATE_HANDSHAKE_TIMEOUT_S:g} s. "
                "Le robot ne répond pas : vérifiez son adresse, le câble, "
                "et que le multicast est bien routé.",
                recoverable=True,
            )

        self._last_state_ok = True

    @staticmethod
    def _read_battery(message: Any) -> float | None:
        """Pourcentage de batterie, ou `None` s'il n'est pas remonté.

        Jamais 0 par défaut : une valeur absente.signale l'absence de donnée,
        et 0 serait une mesure plausible (« batterie vide »).
        """
        for chemin in ("bms.SOC", "bms.soc", "SOC"):
            objet = message
            for attribut in chemin.split("."):
                objet = getattr(objet, attribut, None)
                if objet is None:
                    break
            if isinstance(objet, (int, float)):
                return float(objet)
        return None

    @staticmethod
    def _read_yaw(message: Any) -> float | None:
        """Cap en radians, lu dans `imu.rpy[2]`, ou `None`."""
        imu = getattr(message, "imu", None)
        rpy = getattr(imu, "rpy", None) if imu is not None else None
        if rpy is None:
            return None
        try:
            return float(rpy[2])
        except (TypeError, IndexError, ValueError):
            return None

    @staticmethod
    def _read_position(message: Any) -> tuple[float, float, float] | None:
        """Position estimée, ou `None`."""
        position = getattr(message, "position", None)
        if position is None:
            return None
        try:
            return (float(position[0]), float(position[1]), float(position[2]))
        except (TypeError, IndexError, ValueError):
            return None

    async def disconnect(self) -> None:
        # Toujours tenter l'arrêt avant de couper : laisser une consigne de
        # vitesse active serait dangereux.
        try:
            await self.request_stop()
        except Exception:
            pass
        self._stop_publisher()
        # L'abonné d'état est fermé AVANT la liaison : le laisser ouvert
        # garderait un lecteur DDS actif sur un canal fermé.
        if self._state_channel is not None:
            try:
                self._state_channel.CloseReader()
            except Exception:
                pass
            self._state_channel = None
        self._connected = False
        self._last_state_ok = False
        self._state = RobotState.DISCONNECTED
        self._client = None

    def supports(self, capability: Capability) -> bool:
        return capability in UNITREE_CAPABILITIES

    # -- Boucle de publication --------------------------------------------

    def _start_publisher(self) -> None:
        """Republie la consigne courante en continu.

        RAISON D'ÊTRE : `Move()` est une consigne persistante. Elle doit être
        réémise à haute fréquence (l'exemple officiel utilise dt = 0.005 s).
        Une fois la boucle lancée, un gel ou une panne doit déclencher le
        chien de garde, qui publie une consigne nulle puis `StopMove()`.
        """
        if self._publish_running:
            return
        self._publish_running = True
        self._last_publish_ok = True
        self._shutdown.clear()

        period = self._limits.timing.command_tick_seconds

        def _loop() -> None:
            while self._publish_running:
                with self._lock:
                    vx, vy, vyaw = self._setpoint
                client = self._client
                if client is not None:
                    try:
                        client.Move(vx, vy, vyaw)
                        self._last_publish_ok = True
                    except Exception:
                        self._last_publish_ok = False
                # `wait` sur un événement partagé : permet un arrêt propre.
                self._shutdown.wait(period)

        self._publish_thread = threading.Thread(
            target=_loop, name="go2-publisher", daemon=True
        )
        self._publish_thread.start()

    def _stop_publisher(self) -> None:
        self._publish_running = False
        self._shutdown.set()
        thread = self._publish_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._publish_thread = None

    def _publish(self, vx: float, vy: float, vyaw: float) -> None:
        """Fixe la consigne. La boucle s'occupe de la republication.

        La garde de vitesse est appliquée ici aussi : c'est le dernier point
        de contrôle avant que la valeur n'atteigne le SDK.
        """
        assert_speed_within_limits(
            MotionPlan(
                linear_speed_mps=vx,
                angular_speed_rps=vyaw,
                nominal_duration_s=0.0,
                timeout_s=0.0,
            ),
            self._limits,
        )
        with self._lock:
            self._setpoint = (vx, vy, vyaw)

    # -- État --------------------------------------------------------------

    async def get_status(self) -> Status:
        """Lit l'état si disponible, sinon retourne `unknown`.

        Ne lève jamais : le service doit pouvoir afficher un état inconnu
        plutôt que planter.
        """
        if not self._connected:
            return Status(
                connected=False,
                state=RobotState.DISCONNECTED,
                capabilities=UNITREE_CAPABILITIES,
                blocked_reason="Le service n’est pas connecté au robot.",
            )

        self._read_state()

        blocked: str | None = None
        if not self._last_publish_ok:
            blocked = "Liaison avec le contrôleur du robot interrompue."

        return Status(
            connected=True,
            state=self._state if not blocked else RobotState.ERROR,
            capabilities=UNITREE_CAPABILITIES,
            blocked_reason=blocked,
            position_m=self._position,
            yaw_rad=self._yaw,
            battery_percent=self._battery,
            posture=self._posture,
        )

    def _read_state(self) -> None:
        """Traduit le dernier `SportModeState_` reçu en champs exploitables.

        Source de la forme du message (exemple C++ `go2_sport_client.cpp`) :
            state.position()[0..2]
            state.imu_state().rpy()[2]     # lacet

        La souscription persistante au sujet `rt/sportmodestate` n'est PAS
        encore câblée : `_last_state` reste `None` tant qu'elle ne l'est pas.
        Conséquence assumée : sans état mesuré, aucune instruction de
        déplacement ne sera confirmée « exacte » et toutes se solderont par un
        dépassement de délai. C'est le comportement conservateur voulu.
        """
        cached = self._last_state
        if cached is None:
            self._position = None
            self._yaw = None
            return
        try:
            position = cached.position()
            self._position = (float(position[0]), float(position[1]), float(position[2]))
            rpy = cached.imu_state().rpy()
            self._yaw = float(rpy[2])
        except Exception:
            # Un état illisible vaut « inconnu », pas une valeur inventée.
            self._position = None
            self._yaw = None

    # -- Exécution ---------------------------------------------------------

    async def prepare_run(self) -> None:
        """Relève le robot s'il est assis, avant le premier ordre.

        Même contrat que l'adaptateur WebRTC : un déplacement suppose le
        robot debout.
        """
        if not self.physical_commands_enabled:
            return
        if not self._connected or self._client is None:
            return
        if self._posture in (Posture.STAND, Posture.BALANCE):
            return
        try:
            self._client.StandUp()
            self._posture = Posture.STAND
        except Exception as exc:  # noqa: BLE001
            # Un refus de relèvement n'empêche pas d'exécuter le programme.
            log.warning("Relèvement refusé : %s", exc)

    async def execute_command(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        if not self.physical_commands_enabled:
            raise UnitreeValidationError(
                "L’adaptateur Unitree n’est pas validé : commande refusée."
            )
        if not self._connected or self._client is None:
            raise AdapterError("Le robot n’est pas connecté.", recoverable=True)

        match command.kind:
            case CommandKind.WAIT:
                return await self._do_wait(command.seconds, index, should_stop)
            case CommandKind.STAND_UP:
                return self._do_posture("StandUp", Posture.STAND, index)
            case CommandKind.SIT_DOWN:
                # À VÉRIFIER : la posture assise n'est pas confirmée côté
                # Python. `StandDown` est le repli vérifié.
                return self._do_posture("StandDown", Posture.SIT, index)
            case CommandKind.STOP:
                await self.request_stop()
                # Un bloc « S'arrêter » est une instruction comme une autre :
                # elle s'accomplit et le programme continue.
                return CommandOutcome(
                    index=index, outcome="exact", detail="Arrêt exécuté."
                )
            case _:
                return await self._do_move(command, index, should_stop)

    async def _do_wait(
        self, seconds: float, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        remaining = max(0.0, seconds)
        while remaining > 0:
            if should_stop.requested:
                return CommandOutcome(index=index, outcome="stopped")
            await asyncio.sleep(min(0.05, remaining))
            remaining -= 0.05
        return CommandOutcome(index=index, outcome="exact")

    def _do_posture(self, method: str, posture: Posture, index: int) -> CommandOutcome:
        try:
            fn = getattr(self._client, method)
            fn()
        except Exception as exc:
            raise AdapterError(f"Posture refusée par le robot ({exc}).") from exc
        self._posture = posture
        # Aucune confirmation mesurée disponible : on ne prétend rien.
        return CommandOutcome(
            index=index,
            outcome="exact",
            detail="Consigne envoyée. Aucune confirmation mesurée par le SDK.",
        )

    async def _do_move(
        self, command: RobotCommand, index: int, should_stop: StopSignal
    ) -> CommandOutcome:
        plan = plan_command(command, self._limits)
        if plan is None:
            raise AdapterError(f"Commande non gérée : {command.kind.value}")

        assert_speed_within_limits(plan, self._limits)

        # Point de départ issu de l'ÉTAT MESURÉ, pas d'un calcul théorique.
        start_status = await self.get_status()
        start_xy = (
            (start_status.position_m[0], start_status.position_m[1])
            if start_status.position_m
            else None
        )
        start_yaw = start_status.yaw_rad

        self._start_publisher()
        self._publish(plan.linear_speed_mps, 0.0, plan.angular_speed_rps)
        self._state = RobotState.MOVING

        elapsed = 0.0
        period = self._limits.timing.command_tick_seconds
        try:
            while True:
                if should_stop.requested:
                    await self.request_stop()
                    return CommandOutcome(index=index, outcome="stopped")

                await asyncio.sleep(period)
                elapsed += period

                status = await self.get_status()
                if not status.connected:
                    raise AdapterError("Liaison perdue pendant le déplacement.", recoverable=True)

                if self._reached(plan, start_xy, start_yaw, status):
                    await self.request_stop()
                    return self._outcome(index, plan, start_xy, start_yaw, status, "exact")

                if elapsed >= plan.timeout_s:
                    # Dépassement : arrêt de sécurité. On ne déclare PAS la
                    # cible atteinte.
                    await self.request_stop()
                    return self._outcome(index, plan, start_xy, start_yaw, status, "timeout")
        finally:
            # Toute sortie (y compris une exception) repasse par l'arrêt.
            self._publish(0.0, 0.0, 0.0)
            await self.request_stop()

    def _reached(self, plan, start_xy, start_yaw, status: Status) -> bool:
        """Compare la consigne et l'ÉTAT MESURÉ.

        Si l'état n'est pas lisible, on ne peut rien confirmer : le résultat
        sera un dépassement de délai, ce qui est le comportement conservateur.
        """
        if plan.distance_cm > 0:
            if start_xy is None or status.position_m is None:
                return False
            current = travelled_distance_cm(start_xy, (status.position_m[0], status.position_m[1]))
            # Seuil bas, et non `abs(diff) <= tol` : en cas de dépassement, la
            # seconde formulation laisserait le robot avancer au lieu de s'arrêter.
            return current >= plan.distance_cm - POSITION_TOLERANCE_CM

        if plan.angle_deg > 0:
            if start_yaw is None or status.yaw_rad is None:
                return False
            current = shortest_angular_difference_deg(start_yaw, status.yaw_rad)
            return current >= plan.angle_deg - YAW_TOLERANCE_DEG

        return False

    def _outcome(self, index, plan, start_xy, start_yaw, status, outcome) -> CommandOutcome:
        """Résultat construit à partir de l'état mesuré, jamais de la consigne."""
        if plan.distance_cm > 0 and start_xy and status.position_m:
            measured = travelled_distance_cm(start_xy, (status.position_m[0], status.position_m[1]))
            return CommandOutcome(
                index=index, outcome=outcome, measured_distance_cm=round(measured, 1)
            )
        if plan.angle_deg > 0 and start_yaw is not None and status.yaw_rad is not None:
            measured = shortest_angular_difference_deg(start_yaw, status.yaw_rad)
            return CommandOutcome(
                index=index, outcome=outcome, measured_angle_deg=round(measured, 1)
            )
        return CommandOutcome(
            index=index,
            outcome=outcome,
            detail="Aucune mesure disponible pour cette instruction.",
        )

    async def request_stop(self) -> None:
        """Arrêt immédiat.

        Séquence retenue : consigne nulle republished, puis `StopMove()`.

        À VÉRIFIER : `StopMove()` est-il une commande distincte de `Move(0,0,0)` ?
        L'exemple C++ et Python montrent `StopMove()` comme appel séparé, mais
        leur équivalence réelle n'est pas documentée. Tant que ce n'est pas
        confirmé, on utilise `StopMove()` et on n'affirme aucune garantie
        d'immobilisation.
        """
        self._publish(0.0, 0.0, 0.0)
        self._state = RobotState.IDLE
        client = self._client
        if client is None:
            return
        try:
            client.StopMove()
        except Exception:
            # L'arrêt a échoué : on tente `Damp()`, qui est le mode
            # d'amortissement documenté dans l'exemple officiel.
            # À VÉRIFIER que c'est bien l'arrêt le plus sûr disponible.
            try:
                client.Damp()
            except Exception:
                pass
        self._stop_publisher()

    def __del__(self) -> None:
        # Ne JAMAIS laisser une consigne de vitesse active en mémoire.
        self._publish_running = False
        with self._lock:
            self._setpoint = (0.0, 0.0, 0.0)


def degrees(value: float) -> float:
    """Aide de conversion radians -> degrés (utilisée par les tests)."""
    return value * 180.0 / math.pi