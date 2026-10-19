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
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
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

    async def set_mode(self, mode: str, adult_authorised: bool) -> None:
        """Bascule de mode. Le mode réel est refusé si non validé."""
        if mode == "simulation":
            await self.watchdog.emergency_stop()
            self._mode = "simulation"
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
            "position": (
                {"x": status.position_m[0], "y": status.position_m[1], "z": status.position_m[2]}
                if status.position_m
                else None
            ),
            "yawRad": status.yaw_rad,
            "batteryPercent": status.battery_percent,
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