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
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .adapters.base import RobotAdapter, RobotState
from .adapters.simulated import SimulatedAdapter
from .config import Limits, load_limits
from .execution import (
    FINISH_SAFETY,
    ConcurrentExecutionError,
    ExecutionEngine,
)
from .safety import SafetyWatchdog
from .validation import (
    Capability,
    CommandValidationError,
    parse_program,
    validate_program,
)

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Modèles d'API
# --------------------------------------------------------------------------


class StartRequest(BaseModel):
    """Demande de démarrage d'un programme.

    `adult_authorised` est exigée pour le mode réel. Elle est enregistrée,
    mais la seule autorité reste l'état du service (`_real_mode_enabled`).
    """

    commands: list[dict[str, Any]] = Field(..., max_length=1000)
    adult_authorised: bool = False


class HeartbeatRequest(BaseModel):
    run_id: str = Field(..., max_length=64)


class ModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(simulation|real)$")
    adult_authorised: bool = False


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
        self.engine = ExecutionEngine(self.adapter)
        self.watchdog = SafetyWatchdog(self.engine, self.adapter, self.limits)
        # La simulation est le mode INITIAL, jamais le mode réel.
        self._mode: str = "simulation"
        self._real_mode_enabled: bool = False
        self._status_task: asyncio.Task[None] | None = None
        self._run_task: asyncio.Task[None] | None = None

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
        }


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------


def create_app(adapter: RobotAdapter | None = None) -> FastAPI:
    """Construit l'application. Un adaptateur peut être injecté (tests)."""
    limits = load_limits()
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
            commands = parse_program(payload.commands)
        except CommandValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # 2. Validation AUTORITATIVE (limites, cumuls, capacités réellement
        #    offertes par l'adaptateur connecté — pas toutes par défaut).
        available = frozenset((await adapter.get_status()).capabilities)
        report = validate_program(commands, state.limits, available)
        if not report.valid:
            raise HTTPException(status_code=422, detail=report.first_message())

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
            _run_and_broadcast(state, commands, run_id),
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
    state: "ServiceState", commands: list[Any], run_id: str
) -> None:
    """Exécute le programme en tâche de fond et diffuse sa progression.

    Toute sortie passe par l'arrêt de l'adaptateur : aucune consigne de
    mouvement ne survit à la fin du programme.
    """
    try:
        async for event in state.engine.execute(commands, run_id):
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