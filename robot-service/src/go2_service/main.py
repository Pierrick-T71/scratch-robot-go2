"""Application FastAPI du service robot.

Choix du protocole
------------------
  - HTTP pour les opérations : `GET /api/status`, `POST /api/execution/start`,
    `POST /api/execution/stop`, `POST /api/execution/heartbeat`,
    `POST /api/mode`.
  - WebSocket `/ws/events` pour les événements d'état et la progression.

Le pilotage reste sur HTTP et le WS est en lecture seule : perdre la
connexion WS ne doit jamais interrompre la liaison de sécurité, qui passe par
les battements HTTP.

Sécurité d'accès
----------------
  - écoute sur la boucle locale par défaut (`127.0.0.1`) ;
  - vérification de l'origine sur le WebSocket ;
  - aucune donnée personnelle, aucun compte, aucun appel sortant.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from fastapi import HTTPException

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .adapters.base import RobotAdapter, RobotState
from .adapters.simulated import SimulatedAdapter
from .config import (
    ADJUSTABLE,
    HARD_CEILINGS,
    HARD_FLOORS,
    Limits,
    SettingsError,
    adjustable_settings,
    apply_settings,
    load_limits,
)
from .execution import (
    FINISH_SAFETY,
    ConcurrentExecutionError,
    ExecutionEngine,
)
from .safety import SafetyWatchdog
from .program import (
    Program as StructuredProgram,
    parse_program as parse_structured_program,
    validate_structure,
)
from .validation import (
    Capability,
    CommandValidationError,
)

log = logging.getLogger(__name__)


#: Nom de notre propre logger de paquet.
#:
#: Les modules du service utilisent `logging.getLogger(__name__)`, donc
#: `go2_service` puis `go2_service.adapters.webrtc`, etc.
NOTRE_LOGGER = "go2_service"


def _couper_le_flot_du_sdk() -> None:
    """Empêche le SDK de noyer le journal et de saturer la boucle asyncio.

    ⚠️ Le SDK Unitree journalise CHAQUE message reçu ou envoyé, au
    niveau INFO, sur le logger RACINE (`logging.info(...)`).

    Mesuré sur la machine le 20/10/2026 : **474 Mo de journal en deux
    heures**, soit plusieurs centaines de lignes par seconde. Ce flot
    sature la boucle asyncio, et tout arrive avec retard :

    - l'état lu par le service avait **4,1 s de retard** (médiane) ;
    - la consigne d'arrêt partait avec le même retard.

    Conséquence directe et mesurée : une rotation de 90° demandés
    aboutissait à **139°**, et « avancer de 1 s » durait **5,7 s** et
    parcourait 116 cm au lieu de 30.

    On coupe donc le flot du SDK (logger racine à WARNING) et on relève
    explicitement le nôtre (un logger de paquet n'hérite plus du niveau
    de la racine dès qu'on lui en fixe un).

    ⚠️ Appelée par le POINT D'ENTRÉE (`__main__.main`) et non par
    `create_app` : une application construite dans un test ne doit pas
    modifier la configuration de journalisation de tout le processus.
    """
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger(NOTRE_LOGGER).setLevel(logging.INFO)


# --------------------------------------------------------------------------
# Modèles d'API
# --------------------------------------------------------------------------


class StartRequest(BaseModel):
    """Demande de démarrage d'un programme.

    `adult_authorised` est exigée pour le mode réel. Elle est enregistrée,
    mais la seule autorité reste l'état du service (`_real_mode_enabled`).

    ⚠️ Le champ est `program`, pas `commands`. Un programme contient des
    conditions et des variables, dont la valeur n'est connue qu'à l'exécution :
    l'aplatir avant l'envoi obligerait le frontend à deviner. `extra="forbid"`
    fait qu'un client qui envoie encore `commands` reçoit un 422 explicite
    plutôt qu'un programme vide exécuté en silence.
    """

    model_config = ConfigDict(extra="forbid")

    program: dict[str, Any] = Field(...)
    adult_authorised: bool = False


#: Nom de la variable d'environnement portant la clé AES-128 du robot.
#: Le firmware récent (Go2 >= 1.1.15) refuse le handshake sans elle.
ROBOT_AES_KEY_ENV = "GO2_ROBOT_AES_KEY"

#: Fichier local qui porte la clé, hors dépôt.
#:
#: Le service peut être démarré par n'importe quel script (un redémarrage de
#: la machine, un service systemd, une commande à la main). S'il ne trouve
#: pas la variable d'environnement, il lit ce fichier : la clé ne peut plus
#: disparaître parce qu'un script de démarrage a été oublié.
ROBOT_AES_KEY_FILE = os.environ.get(
    "GO2_ROBOT_ENV_FILE", "/root/go2/robot.env"
)


def _robot_aes_key() -> str | None:
    """Clé AES-128 propre au robot.

    Lue dans l'environnement du service, et à défaut dans le fichier local
    qui la porte (`GO2_ROBOT_ENV_FILE`).

    Volontairement absente du dépôt : c'est un secret lié à une machine.
    """
    valeur = os.environ.get(ROBOT_AES_KEY_ENV, "").strip()
    if valeur:
        return valeur

    try:
        with open(ROBOT_AES_KEY_FILE, encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne.startswith(ROBOT_AES_KEY_ENV + "="):
                    return ligne.split("=", 1)[1].strip() or None
    except OSError:
        pass
    return None


class RobotConnectRequest(BaseModel):
    """Branchement d'un robot réel, déclaré depuis l'interface.

    `extra="forbid"` : un champ mal orthographié doit être REFUSÉ, pas
    accepté silencieusement en valeur par défaut. Ici, `interface` au lieu de
    `network_interface` ferait créer un adaptateur sans interface, donc sans
    joindre le robot — sans le moindre message d'erreur.
    """

    model_config = ConfigDict(extra="forbid")

    robot_ip: str = Field(..., pattern=r"^(\d{1,3}\.){3}\d{1,3}$", max_length=15)
    network_interface: str = Field(..., min_length=1, max_length=32)
    #: `false` = ouvrir le canal et lire l'état. `true` = envoyer aussi la
    #: posture de test, qui fait BOUGER le robot.
    lancer_test: bool = False


class HeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., max_length=64)


class ModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(..., pattern="^(simulation|real)$")
    adult_authorised: bool = False


class SettingsRequest(BaseModel):
    """Modification des limites pédagogiques.

    Réservée à un adulte, et bornée par les plafonds de `config.HARD_CEILINGS`.

    `extra="forbid"` est volontaire : un client qui envoie `adultAuthorised`
    (camelCase) au lieu de `adult_authorised` doit être REJETÉ et non
    silencieusement accepté avec `adult_authorised=False`. C'est exactement le
    type d'erreur qui a fait perdre une session de développement.
    """

    model_config = ConfigDict(extra="forbid")

    adult_authorised: bool = False
    #: Champs omis = inchangés.
    values: dict[str, float] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Gestionnaires
# --------------------------------------------------------------------------


class EventHub:
    """Diffuse les événements à tous les clients WebSocket connectés."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def join(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.add(websocket)

    async def leave(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for client in targets:
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for client in dead:
                    self._clients.discard(client)


@dataclass
class ServiceState:
    """État global du service : adaptateur, mode, moteur, chien de garde."""

    limits: Limits
    adapter: RobotAdapter
    hub: EventHub = field(default_factory=EventHub)

    def __post_init__(self) -> None:
        # Les limites sont transmises au moteur : l'interpréteur doit
        # pouvoir re-borner une valeur calculée à l'exécution.
        self.engine = ExecutionEngine(self.adapter, limits=self.limits)
        self.watchdog = SafetyWatchdog(self.engine, self.adapter, self.limits)
        #: Incrémenté à chaque changement de limites, pour que le frontend
        #: sache que son rapport de vérification est caduc.
        self.settings_revision = 0
        # La simulation est le mode INITIAL, jamais le mode réel.
        self._mode: str = "simulation"
        self._real_mode_enabled: bool = False
        self._status_task: asyncio.Task[None] | None = None
        self._run_task: asyncio.Task[None] | None = None

    def invalidate_report(self) -> None:
        """Signale que les limites ont changé depuis la dernière vérification.

        Le frontend compare cet indicateur pour savoir si le rapport de
        validation qu'il affiche est encore valable.
        """
        self.settings_revision += 1

    @property
    def mode(self) -> str:
        return self._mode

    async def reject_real_execution(self) -> None:
        """
        Empêche toute commande pendant une tentative de branchement.

        Brancher un robot et lancer un programme ne doivent pas pouvoir se
        chevaucher : le moteur doit être libre, et le robot à l'arrêt, avant
        qu'un nouvel adaptateur ne prenne la main.
        """
        if self.engine.is_running:
            raise HTTPException(
                status_code=409,
                detail="Un programme est déjà en cours : arrêtez-le d’abord.",
            )
        await self.watchdog.emergency_stop()

    async def adopt_robot_adapter(self, adapter: Any) -> None:
        """
        Confie le service au robot, après test réussi.

        Le moteur et le chien de garde sont reconstruits : ils gardent
        l'ancien adaptateur dans leurs closures, et le robot ne serait pas
        couvert par le bail de sécurité. Le nouveau chien de garde doit être
        DÉMARRÉ explicitement : sans cela, après un branchement, plus aucun
        bail n'était surveillé.
        """
        await self.watchdog.stop()
        self.adapter = adapter
        self.engine = ExecutionEngine(self.adapter, limits=self.limits)
        self.watchdog = SafetyWatchdog(self.engine, self.adapter, self.limits)
        await self.watchdog.start()
        self._mode = "real"
        self.last_robot_ip = getattr(adapter, "robot_ip", None)

    async def release_robot_adapter(self) -> None:
        """
        Rend le service à la simulation.

        L'arrêt passe par le chien de garde AVANT de fermer la liaison : une
        consigne de vitesse encore publiée quand le canal se ferme laisserait
        le robot partir tout seul.
        """
        await self.watchdog.emergency_stop()
        await self.watchdog.stop()
        ancien = self.adapter
        try:
            await ancien.disconnect()
        except Exception:
            pass
        self.adapter = SimulatedAdapter(self.limits)
        # Le simulateur doit être BRANCHÉ : sans cela, le service revient en
        # simulation en annonçant « non connecté », et l'interface croirait
        # que le robot est hors ligne.
        try:
            await self.adapter.connect()
        except Exception:  # noqa: BLE001
            pass
        self.engine = ExecutionEngine(self.adapter, limits=self.limits)
        self.watchdog = SafetyWatchdog(self.engine, self.adapter, self.limits)
        await self.watchdog.start()
        self._mode = "simulation"

    def report_robot_failure(self, robot_ip: str, message: str) -> None:
        """
        Consigne un échec de branchement.

        Le service reste en simulation : un robot injoignable ne doit jamais
        laisser croire qu'un programme part vers la machine.
        """
        self.last_robot_ip = robot_ip
        self.last_robot_error = message
        self._mode = "simulation"

    async def set_mode(self, mode: str, adult_authorised: bool) -> None:
        """Bascule de mode. Le mode réel est refusé si non validé."""
        if mode == "simulation":
            await self.release_robot_adapter()
            return

        # Mode réel.
        if not adult_authorised:
            raise PermissionError(
                "Le mode robot réel doit être autorisé par un adulte."
            )
        if not self.adapter.physical_commands_enabled:
            raise PermissionError(
                "Le pilotage du robot réel n’est pas validé sur cette machine. "
                "L’adaptateur reste en simulation (voir docs/ROBOT_SETUP.md)."
            )
        if self.engine.is_running:
            raise PermissionError(
                "Impossible de changer de mode pendant une exécution."
            )
        self._mode = "real"

    async def status_payload(self) -> dict[str, Any]:
        status = await self.adapter.get_status()
        return {
            "connected": status.connected,
            "mode": self._mode,
            "capabilities": sorted(c.value for c in status.capabilities),
            "executing": self.engine.is_running,
            "blockedReason": status.blocked_reason,
            "safetyReason": status.safety_reason,
            "recoveryReason": status.recovery_reason,
            "position": (
                {"x": status.position_m[0], "y": status.position_m[1], "z": status.position_m[2]}
                if status.position_m
                else None
            ),
            "yawRad": status.yaw_rad,
            "batteryPercent": status.battery_percent,
            # Dernière posture DEMANDÉE au robot. Ce n'est pas une mesure :
            # le SDK ne publie pas la posture réelle. `null` = inconnue.
            "posture": status.posture.value if status.posture else None,
            "settingsRevision": self.settings_revision,
        }


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------


def create_app(adapter: RobotAdapter | None = None) -> FastAPI:
    """Construit l'application. Un adaptateur peut être injecté (tests).

    `load_limits()` est mis en cache et renvoie donc le MÊME objet à chaque
    appel. Or `apply_settings()` modifie ces limites en place : sans copie,
    une application créée dans un test altérerait le service des autres, et
    l'ordre d'exécution des tests deviendrait significatif. On copie donc.
    """
    limits = copy.deepcopy(load_limits())
    if adapter is None:
        adapter = SimulatedAdapter(limits)

    state = ServiceState(limits=limits, adapter=adapter)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Cycle de vie du service.

        L'arrêt passe TOUJOURS par `emergency_stop()` avant toute fermeture :
        quitter le service ne doit jamais laisser une consigne de mouvement
        active sur le robot.
        """
        await adapter.connect()
        await state.watchdog.start()
        state._status_task = asyncio.create_task(_status_pusher(state), name="go2-status")
        log.info("Service démarré en mode %s", state.mode)
        try:
            yield
        finally:
            await state.watchdog.emergency_stop()
            await state.watchdog.stop()
            for task in (state._run_task, state._status_task):
                if task is None:
                    continue
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await adapter.disconnect()
            log.info("Service arrêté proprement")

    app = FastAPI(
        title="GO2 Scratch — service robot",
        version="0.1.0",
        lifespan=lifespan,
        description=(
            "Service intermédiaire entre l'éditeur Blockly et le robot Unitree Go2. "
            "Ne publie jamais sur Internet. Simulation par défaut."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(limits.service.allowed_origin),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.state.service = state

    # -- Cycle de vie ------------------------------------------------------

    # NOTE : le cycle de vie est géré par `lifespan` ci-dessus. Les routes
    # ci-dessous n'ont donc plus de gestionnaires `on_event` dépréciés.

    # -- API ---------------------------------------------------------------

    @app.get("/api/status")
    async def get_status() -> dict[str, Any]:
        return await state.status_payload()

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        """Réglages en vigueur + bornes autorisées.

        Les bornes (`floors` / `ceilings`) sont fournies par le service : la
        interface n'a pas à les connaître et ne peut pas les élargir.
        """
        return {
            "values": adjustable_settings(limits),
            "bounds": {
                name: {"min": HARD_FLOORS[name], "max": getattr(HARD_CEILINGS, ceiling_attr)}
                for name, ceiling_attr in ADJUSTABLE.items()
            },
            "editable": state.engine.is_running is False,
        }

    @app.post("/api/settings")
    async def post_settings(payload: SettingsRequest) -> dict[str, Any]:
        """Applique des réglages. Refusé si une exécution est en cours.

        Refuser en cours d'exécution évite qu'un programme soit validé avec
        d'autres limites que celles qui seront appliquées à son exécution.
        """
        from fastapi import HTTPException

        if not payload.adult_authorised:
            raise HTTPException(
                status_code=403,
                detail="Seul un adulte peut modifier les réglages.",
            )
        if state.engine.is_running:
            raise HTTPException(
                status_code=409,
                detail="Attends la fin du programme avant de modifier les réglages.",
            )
        try:
            applied = apply_settings(limits, payload.values)
        except SettingsError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        log.info("Réglages mis à jour par un adulte : %s", applied)
        # Un changement de limites invalide le rapport précédent.
        state.invalidate_report()
        return {
            "values": applied,
            "bounds": {
                name: {"min": HARD_FLOORS[name], "max": getattr(HARD_CEILINGS, ceiling_attr)}
                for name, ceiling_attr in ADJUSTABLE.items()
            },
        }

    @app.post("/api/mode")
    async def set_mode(payload: ModeRequest) -> dict[str, Any]:
        try:
            await state.set_mode(payload.mode, payload.adult_authorised)
        except PermissionError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return await state.status_payload()

    @app.post("/api/execution/start")
    async def start(payload: StartRequest) -> dict[str, Any]:
        from fastapi import HTTPException

        if state.engine.is_running:
            raise HTTPException(
                status_code=409, detail="Un programme est déjà en cours."
            )

        # 1. Validation de la FORME. Une donnée forgée est refusée ici.
        try:
            program = parse_structured_program(payload.program)
        except CommandValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # 2. Validation AUTORITAIRE : durées, angles, imbrication, cumuls.
        #    C'est la SEULE validation opposable ; celle du frontend n'est
        #    qu'un confort d'affichage.
        structure = validate_structure(program, state.limits)
        if not structure.valid:
            raise HTTPException(status_code=422, detail=structure.first_message())

        # 3. Garde-fou mode réel : autorisation adulte ET robot connecté.
        if state.mode == "real":
            if not payload.adult_authorised:
                raise HTTPException(
                    status_code=403,
                    detail="Le démarrage réel doit être autorisé par un adulte.",
                )
            status = await adapter.get_status()
            if not status.connected:
                raise HTTPException(
                    status_code=409,
                    detail="Le robot n’est pas connecté.",
                )
            if status.state in (RobotState.ERROR, RobotState.DISCONNECTED):
                raise HTTPException(
                    status_code=409,
                    detail="Le robot n’est pas dans un état permettant de bouger.",
                )

        run_id = state.engine.new_run_id()

        # L'exécution part en tâche de fond : la requête HTTP répond tout de
        # suite avec l'identifiant. La progression est diffusée sur le
        # WebSocket. Aucun client ne peut ainsi bloquer l'exécution.
        task = asyncio.create_task(
            _run_and_broadcast(state, program, run_id),
            name=f"go2-exec-{run_id}",
        )
        state._run_task = task

        return {"accepted": True, "runId": run_id}

    @app.post("/api/robot/connect")
    async def robot_connect(payload: RobotConnectRequest) -> dict[str, Any]:
        """
        Branche un robot réel et, sur demande, lance un test physique.

        Le passage en réel est conditionné au SUCCÈS de ce test : le service
        ne remplace jamais son adaptateur avant que la liaison soit prouvée.
        Si le robot ne répond pas, la simulation reste active — l'inverse
        n'est jamais vrai.
        """
        from .adapters.webrtc import WebRTCAdapter

        state.reject_real_execution()

        # Un seul canal à la fois : le robot refuse un second client. Sans ce
        # relâchement, un deuxième essai échouerait alors que le robot est
        # parfaitement joignable — l'ancienne liaison resterait ouverte.
        if state.mode == "real":
            await state.release_robot_adapter()

        try:
            candidat: WebRTCAdapter = WebRTCAdapter(
                state.limits,
                payload.robot_ip,
                aes_key=_robot_aes_key(),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"Construction de l’adaptateur impossible ({exc}).",
            ) from exc

        try:
            # Le verrou de la classe reste fermé : on ouvre CETTE instance,
            # uniquement parce qu'un adulte a saisi une adresse et demandé
            # explicitement la connexion.
            candidat.enable_physical_commands()
            await candidat.connect()
        except Exception as exc:
            await candidat.disconnect()
            state.report_robot_failure(payload.robot_ip, str(exc))
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Connexion au robot {payload.robot_ip} impossible : {exc}. "
                    "L’application reste en simulation."
                ),
            ) from exc

        rapport: dict[str, object] = {
            "robot_ip": payload.robot_ip,
            "interface": getattr(
                candidat, "network_interface", payload.network_interface
            ),
            "connecte": True,
            "test_lance": payload.lancer_test,
            "message": "",
        }

        if payload.lancer_test:
            resultat = await candidat.self_test()
            rapport.update(resultat)
            if not resultat.get("succes"):
                rapport["connecte"] = False

        if not rapport.get("connecte"):
            await candidat.disconnect()
            state.report_robot_failure(payload.robot_ip, str(rapport.get("message", "")))
            raise HTTPException(
                status_code=502,
                detail=str(rapport.get("message", "Le robot n’a pas répondu.")),
            )

        # Le robot est là : on lui confie le service, jusqu'au prochain arrêt.
        await state.adopt_robot_adapter(candidat)
        return rapport

    @app.post("/api/robot/disconnect")
    async def robot_disconnect() -> dict[str, Any]:
        """Revient en simulation et immobilise le robot."""
        state.release_robot_adapter()
        return {"simulation": True}

    @app.get("/api/robot/lidar")
    async def robot_lidar() -> dict[str, Any]:
        """La carte du lidar du robot.

        `volume` est le volume de voxels, en base64 (les sommets sont les
        indices dans la grille) : c'est ce que l'application affiche, en 3D.
        `points` est la même carte vue du dessus, en mètres autour du robot.

        Tout est vide quand le lidar n'envoie rien : on ne dessine jamais
        une carte inventée.
        """
        points = await state.adapter.lidar_points()
        volume = await state.adapter.lidar_volume()
        return {
            "points": points or [],
            "volume": volume,
            "actif": bool(points or volume),
        }

    @app.get("/api/robot/camera")
    async def robot_camera() -> StreamingResponse:
        """Flux de la caméra du robot, au format MJPEG.

        Le service reçoit les images du robot et les relaie : la clé AES ne
        quitte jamais la machine qui parle au robot.

        Réponse `503` quand il n'y a pas de caméra (simulation, robot non
        branché) : l'interface montre alors son illustration, et le dit.
        """
        from fastapi import HTTPException

        async def generateur():
            derniere = b""
            while True:
                image = await state.adapter.camera_frame()
                if image and image != derniere:
                    derniere = image
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(image)).encode() + b"\r\n\r\n"
                        + image
                        + b"\r\n"
                    )
                await asyncio.sleep(0.1)

        # Une seule vérification avant d'ouvrir le flux : la caméra peut
        # ne pas être prête, et un flux vide n'apprend rien à l'interface.
        if await state.adapter.camera_frame() is None:
            raise HTTPException(
                status_code=503,
                detail="La caméra du robot n’est pas disponible.",
            )

        return StreamingResponse(
            generateur(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/execution/stop")
    async def stop() -> dict[str, Any]:
        if not state.engine.request_stop():
            # Aucun programme en cours : on demande tout de même l'arrêt de
            # l'adaptateur, pour ne jamais laisser une consigne résiduelle.
            await adapter.request_stop()
        return {"stopping": True}

    @app.post("/api/execution/heartbeat")
    async def heartbeat(payload: HeartbeatRequest) -> dict[str, Any]:
        state.engine.notify_heartbeat(_monotonic())
        return {"ok": True}

    # -- WebSocket ---------------------------------------------------------

    @app.websocket("/ws/events")
    async def events(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in state.limits.service.allowed_origin:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await state.hub.join(websocket)
        try:
            await websocket.send_json(
                {"type": "status", "status": await state.status_payload()}
            )
            while True:
                # On ne reçoit rien du frontend : ce canal est en lecture
                # seule. Le battement de sécurité passe par HTTP.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            log.debug("Connexion websocket terminée", exc_info=True)
        finally:
            await state.hub.leave(websocket)

    return app


async def _run_and_broadcast(
    state: "ServiceState", program: "StructuredProgram", run_id: str
) -> None:
    """Interprète puis exécute le programme, en tâche de fond.

    Toute sortie passe par l'arrêt de l'adaptateur : aucune consigne de
    mouvement ne survit à la fin du programme.
    """
    try:
        async for event in state.engine.execute_program(program, run_id):
            if event.type == "execution_finished" and event.reason == FINISH_SAFETY:
                log.warning("Exécution arrêtée par la sécurité.")
            await state.hub.broadcast(
                {
                    "type": event.type,
                    "index": event.index,
                    "label": event.label,
                    "outcome": event.outcome,
                    "measured": event.measured,
                    "reason": event.reason,
                    "message": event.message,
                }
            )
    except ConcurrentExecutionError:
        await state.hub.broadcast(
            {
                "type": "error",
                "message": "Un programme est déjà en cours d’exécution.",
            }
        )
    except Exception:
        log.exception("Exécution interrompue par une erreur interne.")
        await state.hub.broadcast(
            {
                "type": "error",
                "message": "Le service a rencontré une erreur et a arrêté le robot.",
            }
        )
        await state.watchdog.emergency_stop()


async def _status_pusher(state: ServiceState) -> None:
    """Pousse l'état robot à intervalle régulier sur le WebSocket."""
    try:
        while True:
            await asyncio.sleep(state.limits.safety.frontend_poll_timeout_ms / 1000.0)
            payload = await state.status_payload()
            await state.hub.broadcast({"type": "status", "status": payload})
    except asyncio.CancelledError:
        raise


def _monotonic() -> float:
    return time.monotonic()