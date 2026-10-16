"""Chargement de la configuration de sécurité.

La configuration provient du MÊME fichier que le frontend
(`shared/safety-limits.json`). C'est volontaire : une seule source de vérité,
aucune dérive possible entre l'interface et l'autorité.

Ce module est le seul endroit où le fichier est lu et validé.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# robot-service/src/go2_service/config.py -> racine du dépôt
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIMITS_PATH = _REPO_ROOT / "shared" / "safety-limits.json"


class ConfigurationError(RuntimeError):
    """Le fichier de configuration est absent ou invalide."""


@dataclass(frozen=True)
class MotionLimits:
    max_linear_speed: float
    max_angular_speed: float
    max_distance_per_step_cm: float
    max_angle_per_step_deg: float
    min_distance_per_step_cm: float
    min_angle_per_step_deg: float


@dataclass(frozen=True)
class TimingLimits:
    min_wait_seconds: float
    max_wait_seconds: float
    command_tick_seconds: float
    control_period_ms: int
    safety_stop_latency_ms: int


@dataclass(frozen=True)
class ProgramLimits:
    max_total_steps: int
    max_repeat_count: int
    max_nested_repeat_depth: int
    max_program_seconds: float
    max_total_distance_cm: float
    max_total_angle_deg: float


@dataclass(frozen=True)
class SafetyLimits:
    lease_timeout_ms: int
    heartbeat_interval_ms: int
    frontend_poll_timeout_ms: int
    post_stop_verification_ms: int
    max_command_retries: int


@dataclass(frozen=True)
class ServiceConfig:
    host: str
    port: int
    allowed_origin: tuple[str, ...]


@dataclass(frozen=True)
class Limits:
    motion: MotionLimits
    timing: TimingLimits
    program: ProgramLimits
    safety: SafetyLimits
    service: ServiceConfig


def _require(data: dict[str, Any], key: str, kind: type) -> Any:
    """Lit une clé obligatoire et vérifie grossièrement son type.

    Tolère `int` là où un `float` est attendu : le JSON distingue `200` et
    `200.0`, ce qui n'a aucun sens pour une limite physique.
    """
    if key not in data:
        raise ConfigurationError(f"Clé de configuration manquante : {key!r}")
    value = data[key]

    # bool est un sous-type de int : on l'écarte explicitement, car `true`
    # ne doit pas pouvoir passer pour la vitesse 1.0.
    if isinstance(value, bool):
        raise ConfigurationError(f"La clé {key!r} ne doit pas être un booléen.")

    if kind is float and isinstance(value, int):
        return float(value)

    if not isinstance(value, kind):
        raise ConfigurationError(
            f"La clé {key!r} doit être de type {kind.__name__}, reçu {type(value).__name__}."
        )
    return value


@lru_cache(maxsize=1)
def load_limits() -> Limits:
    """Lit et valide `shared/safety-limits.json`.

    Le résultat est mis en cache : le service ne recharge pas le fichier en
    boucle, et une modification à chaud n'est pas supportée (c'est volontaire,
    cela évite qu'une limite change en pleine exécution).
    """
    if not _LIMITS_PATH.is_file():
        raise ConfigurationError(
            f"Fichier de configuration introuvable : {_LIMITS_PATH}. "
            "Le dépôt est-il complet ?"
        )

    try:
        raw = json.loads(_LIMITS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"JSON invalide dans {_LIMITS_PATH} : {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigurationError("La configuration doit être un objet JSON.")

    for section in ("motion", "timing", "program", "safety", "service"):
        if section not in raw or not isinstance(raw[section], dict):
            raise ConfigurationError(f"Section de configuration manquante : {section!r}")

    m, t, p, s, svc = (
        raw["motion"],
        raw["timing"],
        raw["program"],
        raw["safety"],
        raw["service"],
    )

    origins = svc.get("allowedOrigin", [])
    if not isinstance(origins, list) or not all(isinstance(o, str) for o in origins):
        raise ConfigurationError("service.allowedOrigin doit être une liste de chaînes.")

    return Limits(
        motion=MotionLimits(
            max_linear_speed=_require(m, "maxLinearSpeed", float),
            max_angular_speed=_require(m, "maxAngularSpeed", float),
            max_distance_per_step_cm=_require(m, "maxDistancePerStepCm", float),
            max_angle_per_step_deg=_require(m, "maxAnglePerStepDeg", float),
            min_distance_per_step_cm=_require(m, "minDistancePerStepCm", float),
            min_angle_per_step_deg=_require(m, "minAnglePerStepDeg", float),
        ),
        timing=TimingLimits(
            min_wait_seconds=_require(t, "minWaitSeconds", float),
            max_wait_seconds=_require(t, "maxWaitSeconds", float),
            command_tick_seconds=_require(t, "commandTickSeconds", float),
            control_period_ms=_require(t, "controlPeriodMs", int),
            safety_stop_latency_ms=_require(t, "safetyStopLatencyMs", int),
        ),
        program=ProgramLimits(
            max_total_steps=_require(p, "maxTotalSteps", int),
            max_repeat_count=_require(p, "maxRepeatCount", int),
            max_nested_repeat_depth=_require(p, "maxNestedRepeatDepth", int),
            max_program_seconds=_require(p, "maxProgramSeconds", float),
            max_total_distance_cm=_require(p, "maxTotalDistanceCm", float),
            max_total_angle_deg=_require(p, "maxTotalAngleDeg", float),
        ),
        safety=SafetyLimits(
            lease_timeout_ms=_require(s, "leaseTimeoutMs", int),
            heartbeat_interval_ms=_require(s, "heartbeatIntervalMs", int),
            frontend_poll_timeout_ms=_require(s, "frontendPollTimeoutMs", int),
            post_stop_verification_ms=_require(s, "postStopVerificationMs", int),
            max_command_retries=_require(s, "maxCommandRetries", int),
        ),
        service=ServiceConfig(
            host=_require(svc, "host", str),
            port=_require(svc, "port", int),
            allowed_origin=tuple(origins),
        ),
    )