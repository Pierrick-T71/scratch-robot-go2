"""Pilotage manuel au clavier (ZQSD et flèches).

Le robot ne reçoit une consigne de vitesse que tant que l'interface renouvelle
la demande. Sans renouvellement, le contrôleur envoie un arrêt au bout de
``MANUAL_TTL_S`` : une touche bloquée, un onglet fermé ou un réseau coupé ne
doivent jamais laisser le robot marcher tout seul.

Le mode manuel ne consulte PAS la carte du lidar : un adulte pilote le robot
à vue, et le contrôle de place du service ralentissait chaque mouvement. Il
ne remplace ni l'anti-obstacle interne du Go2, ni le chien de garde, ni la
surveillance d'un adulte.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from .adapters.base import AdapterError, RobotAdapter, SafetyInterrupt

log = logging.getLogger(__name__)

#: Directions acceptées.
DIRECTIONS = (
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

#: Durée maximale entre deux renouvellements de l'interface.
#:
#: L'interface renouvelle toutes les 200 ms, mais le service peut être occupé
#: par le lidar ou la caméra et répondre en plus d'une seconde. Avec un bail
#: trop court, le robot s'arrêtait alors que l'enfant tenait encore la touche :
#: le mouvement devenait haché et semblait beaucoup plus lent.
MANUAL_TTL_S = 2.0

#: Période de la boucle de pilotage.
MANUAL_TICK_S = 0.1

#: Vitesse du mode manuel.
#:
#: Le mode manuel est réservé à un adulte et volontairement plus vif que les
#: programmes : 0,6 m/s avance franchement et donne un trot naturel au Go2. Ces valeurs
#: ne sont PAS lues dans ``shared/safety-limits.json`` : elles ne doivent pas
#: élargir les limites des programmes de l'enfant.
MANUAL_SPEED_MPS = 0.6

#: Vitesse de rotation en mode manuel.
#:
#: 1,0 rad/s (~57°/s) offre le bon équilibre entre réactivité et précision :
#: une frappe brève au clavier permet un ajustement fin du cap sans survirage.
MANUAL_TURN_SPEED_RPS = 1.0

#: Vitesse lente pour le déplacement en mode accroupi (crawl / creep).
CRAWL_SPEED_MPS = 0.20
CRAWL_TURN_SPEED_RPS = 0.50


class ManualNotActive(RuntimeError):
    """Le mode manuel n'a pas été ouvert."""


class ManualControl:
    """Consigne de vitesse continue, avec arrêt automatique au relâchement."""

    def __init__(self, adapter: RobotAdapter) -> None:
        self._adapter = adapter

        self._active = False
        self._direction: str | None = None
        self._active_source: str | None = None
        self._deadline = 0.0
        self._blocked_reason: str | None = None
        self._prepared = False
        self._seq_by_source: dict[str, int] = {}
        self._crouch_mode = False

        self._task: asyncio.Task[None] | None = None
        self._prepare_task: asyncio.Task[None] | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def direction(self) -> str | None:
        return self._direction

    @property
    def active_source(self) -> str | None:
        """Source active ('keyboard' ou 'mobile') si une commande est en cours."""
        if self._direction is not None and time.monotonic() < self._deadline:
            return self._active_source
        return None

    @property
    def _last_seq(self) -> int:
        return max(self._seq_by_source.values()) if self._seq_by_source else 0

    @_last_seq.setter
    def _last_seq(self, val: int) -> None:
        self._seq_by_source["default"] = val

    @property
    def blocked_reason(self) -> str | None:
        return self._blocked_reason

    @property
    def crouch_mode(self) -> bool:
        """Indique si le mode accroupi (vitesse lente, StaticWalk) est actif."""
        return self._crouch_mode

    @property
    def speed_mps(self) -> float:
        """Vitesse fixée par le service, jamais par le client."""
        if self._crouch_mode:
            return CRAWL_SPEED_MPS
        return MANUAL_SPEED_MPS

    @property
    def turn_speed_rps(self) -> float:
        """Vitesse de rotation fixée par le service."""
        if self._crouch_mode:
            return CRAWL_TURN_SPEED_RPS
        return MANUAL_TURN_SPEED_RPS

    def start(self) -> None:
        """Ouvre une session. Ne fait PAS bouger le robot."""
        if not self._active:
            self._active = True
            self._prepared = False
            self._seq_by_source.clear()
            self._prepare_once()
            self._task = asyncio.create_task(self._loop(), name="go2-manual")
        # Une nouvelle entrée dans le mode efface un ancien blocage.
        self._direction = None
        self._active_source = None
        self._blocked_reason = None
        self._deadline = 0.0
        self._crouch_mode = False
        log.info("Mode manuel ouvert.")

    async def set_direction(
        self, direction: str | None, seq: int = 0, source: str = "keyboard"
    ) -> tuple[bool, str | None]:
        """Démarre/renouvelle une direction, ou arrête le mouvement.

        Retourne ``(bloqué, message)``. Quand ``direction`` est ``None``, la
        touche a été relâchée : le robot s'arrête immédiatement et le blocage
        est effacé.

        ``seq`` est le numéro croissant de la requête pour chaque ``source``.
        ``source`` identifie le contrôleur ('keyboard', 'mobile').
        """
        if not self._active:
            raise ManualNotActive("Le mode manuel n’est pas ouvert.")

        now = time.monotonic()
        last_seq = self._seq_by_source.get(source, 0)
        if seq <= 0:
            seq = last_seq + 1
        if seq <= last_seq:
            return False, None
        self._seq_by_source[source] = seq

        # Arbitrage : si une autre source contrôle activement le robot
        if (
            self._active_source is not None
            and self._active_source != source
            and self._direction is not None
            and now < self._deadline
        ):
            if direction is None:
                # Un relâchement d'une source inactive n'interrompt pas la source active
                return False, None
            return True, f"Le robot est déjà piloté par {self._active_source}."

        if direction is None:
            self._direction = None
            self._active_source = None
            self._blocked_reason = None
            self._deadline = 0.0
            self._stop_motion()
            return False, None

        if direction not in DIRECTIONS:
            raise ValueError(f"Direction inconnue : {direction}")

        if self._blocked_reason is not None:
            # Le robot n'est pas prêt (préparation impossible, sécurité
            # interne) : on ne renvoie pas de vitesse tant que la touche
            # n'a pas été relâchée.
            return True, self._blocked_reason

        self._direction = direction
        self._active_source = source
        self._deadline = now + MANUAL_TTL_S
        return False, None

    async def jump(self, source: str = "keyboard") -> tuple[bool, str | None]:
        """Déclenche un saut immédiat en mode manuel.

        Retourne ``(bloqué, message)``.
        """
        if not self._active:
            raise ManualNotActive("Le mode manuel n’est pas ouvert.")

        now = time.monotonic()
        if (
            self._active_source is not None
            and self._active_source != source
            and self._direction is not None
            and now < self._deadline
        ):
            return True, f"Le robot est déjà piloté par {self._active_source}."

        if self._blocked_reason is not None:
            return True, self._blocked_reason

        # Arrête d'abord toute consigne de déplacement continu
        self._direction = None
        self._active_source = source
        self._deadline = 0.0
        self._stop_motion()

        sauteur = getattr(self._adapter, "manual_jump", None)
        if not callable(sauteur):
            return True, "Le saut manuel n’est pas disponible sur ce robot."

        try:
            await sauteur()
            return False, None
        except SafetyInterrupt as exc:
            self._block(str(exc))
            return True, str(exc)
        except AdapterError as exc:
            self._block(str(exc))
            return True, str(exc)
        except Exception as exc:  # noqa: BLE001
            log.exception("Saut manuel impossible.")
            self._block(f"Le robot n’a pas pu sauter ({exc}).")
            return True, str(exc)

    async def set_crouch_mode(self, enabled: bool) -> tuple[bool, str | None]:
        """Active ou désactive le mode accroupi (déplacement lent, stable et fluide)."""
        if not self._active:
            raise ManualNotActive("Le mode manuel n’est pas ouvert.")

        target = bool(enabled)
        if target == self._crouch_mode:
            return False, None

        # Arrête d'abord toute consigne de déplacement en cours
        self._direction = None
        self._active_source = None
        self._deadline = 0.0
        self._stop_motion()

        try:
            if target:
                entrer = getattr(self._adapter, "enter_crouch_mode", None)
                if callable(entrer):
                    await entrer()
                self._crouch_mode = True
                log.info("Mode accroupi manuel activé.")
            else:
                sortir = getattr(self._adapter, "exit_crouch_mode", None)
                if callable(sortir):
                    await sortir()
                self._crouch_mode = False
                log.info("Mode accroupi manuel désactivé.")
            return False, None
        except SafetyInterrupt as exc:
            self._block(str(exc))
            return True, str(exc)
        except AdapterError as exc:
            self._block(str(exc))
            return True, str(exc)
        except Exception as exc:  # noqa: BLE001
            log.exception("Changement de mode accroupi impossible.")
            self._block(f"Le robot n’a pas pu modifier sa posture ({exc}).")
            return True, str(exc)

    async def stop(self) -> None:
        """Ferme la session et immobilise le robot."""
        if not self._active:
            return

        if self._crouch_mode:
            sortir = getattr(self._adapter, "exit_crouch_mode", None)
            if callable(sortir):
                with contextlib.suppress(Exception):
                    await sortir()
            self._crouch_mode = False

        self._active = False
        self._direction = None
        self._active_source = None
        self._blocked_reason = None
        self._deadline = 0.0
        self._prepared = False
        self._seq_by_source.clear()

        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        prepare = self._prepare_task
        self._prepare_task = None
        if prepare is not None:
            prepare.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await prepare

        self._stop_motion()
        try:
            # Termine proprement le programme manuel : le relevage automatique
            # redevient possible et aucune consigne ne survit à la session.
            await self._adapter.request_stop()
        except Exception:  # noqa: BLE001
            log.exception("Arrêt du mode manuel : l’adaptateur a échoué.")
        log.info("Mode manuel fermé.")

    def _stop_motion(self) -> None:
        """Arrêt immédiat, sans attendre le réseau."""
        stopper = getattr(self._adapter, "manual_stop", None)
        if callable(stopper):
            try:
                stopper()
            except Exception:  # noqa: BLE001
                log.exception("Arrêt manuel : l’adaptateur a échoué.")
            return

        # Adaptateur sans méthode manuelle : on utilise l'arrêt générique.
        try:
            asyncio.get_running_loop().create_task(self._adapter.request_stop())
        except RuntimeError:
            pass

    async def _loop(self) -> None:
        """Maintient la vitesse jusqu'au relâchement, puis s'arrête."""
        try:
            while self._active:
                direction = self._direction
                now = time.monotonic()

                if direction is None:
                    await asyncio.sleep(MANUAL_TICK_S)
                    continue

                if now > self._deadline:
                    # Personne ne renouvelle : l'interface a probablement
                    # disparu. On s'arrête sans attendre une nouvelle requête.
                    log.warning("Pilotage manuel : bail expiré, arrêt du robot.")
                    self._direction = None
                    self._active_source = None
                    self._deadline = 0.0
                    self._stop_motion()
                    continue

                securite = getattr(self._adapter, "safety_stop_reason", None)
                if securite:
                    self._block(str(securite))
                    continue

                if not self._prepared:
                    self._prepare_once()
                    await asyncio.sleep(MANUAL_TICK_S)
                    continue

                try:
                    emettre = getattr(self._adapter, "manual_velocity", None)
                    if not callable(emettre):
                        self._block(
                            "Le pilotage manuel n’est pas disponible sur ce robot."
                        )
                        continue
                    emettre(direction, self.speed_mps, self.turn_speed_rps)
                except SafetyInterrupt as exc:
                    self._block(str(exc))
                    continue
                except AdapterError as exc:
                    self._block(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001
                    log.exception("Pilotage manuel : commande impossible.")
                    self._block(f"Le robot n’a pas pu bouger ({exc}).")
                    continue

                await asyncio.sleep(MANUAL_TICK_S)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Pilotage manuel : boucle interrompue.")
            self._active = False
            self._direction = None
            self._active_source = None
            self._stop_motion()
        finally:
            if self._active:
                # Sortie inattendue : ne jamais laisser une vitesse active.
                self._stop_motion()

    def _prepare_once(self) -> None:
        """Lance la préparation du robot, sans bloquer la boucle."""
        task = self._prepare_task
        if task is not None and not task.done():
            return
        self._prepare_task = asyncio.create_task(
            self._prepare(), name="go2-manual-prepare"
        )

    async def _prepare(self) -> None:
        try:
            preparer = getattr(self._adapter, "manual_prepare", None)
            if not callable(preparer):
                self._block(
                    "Le pilotage manuel n’est pas disponible sur ce robot."
                )
                return
            await preparer()
            self._prepared = True
        except SafetyInterrupt as exc:
            self._block(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Préparation du pilotage manuel impossible.")
            self._block(str(exc))

    def _block(self, reason: str) -> None:
        """Arrête et empêche la reprise tant que la touche n'est pas relâchée."""
        self._blocked_reason = reason
        self._direction = None
        self._active_source = None
        self._deadline = 0.0
        self._stop_motion()
        log.warning("Pilotage manuel arrêté : %s", reason)
