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


# Les classes de limites sont VOLATILES (non gelées) et non immuables : les
# réglages pédagogiques doivent pouvoir les ajuster depuis l'interface. Les
#cales dures (`HardCeilings` ci-dessous) restent, elles, des constantes de code.


@dataclass
class MotionLimits:
    max_linear_speed: float
    max_angular_speed: float
    max_distance_per_step_cm: float
    max_angle_per_step_deg: float
    min_distance_per_step_cm: float
    min_angle_per_step_deg: float


@dataclass
class TimingLimits:
    min_wait_seconds: float
    max_wait_seconds: float
    command_tick_seconds: float
    control_period_ms: int
    safety_stop_latency_ms: int


@dataclass
class ProgramLimits:
    max_total_steps: int
    max_repeat_count: int
    max_nested_repeat_depth: int
    max_program_seconds: float
    max_total_distance_cm: float
    max_total_angle_deg: float


@dataclass
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


@dataclass
class Limits:
    motion: MotionLimits
    timing: TimingLimits
    program: ProgramLimits
    safety: SafetyLimits
    service: ServiceConfig


@dataclass(frozen=True)
class HardCeilings:
    """Plafonds NON MODIFIABLES, écrits ici dans le code.

    Ce sont les valeurs de `shared/safety-limits.json` au moment de la
    livraison. L'interface peut régler les limites entre ces plafonds et un
    plancher, jamais au-delà.

    Conséquence : un client modifié ne peut pas s'attribuer des droits
    supérieurs en appelant l'API de réglage. Pour relever un plafond, il faut
    modifier ce fichier puis redémarrer le service — acte visible en revue de
    code, et non en session pédagogique.
    """

    max_linear_speed: float = 0.30
    max_angular_speed: float = 0.50
    max_distance_per_step_cm: float = 200.0
    max_angle_per_step_deg: float = 180.0
    max_wait_seconds: float = 10.0
    max_total_steps: int = 500
    max_repeat_count: int = 20
    max_program_seconds: float = 120.0
    max_total_distance_cm: float = 1500.0
    max_total_angle_deg: float = 3600.0


#: Valeurs plancher : en dessous, les missions deviennent impraticables.
HARD_FLOORS: dict[str, float] = {
    "max_linear_speed": 0.10,
    "max_angular_speed": 0.20,
    "max_distance_per_step_cm": 40.0,
    "max_angle_per_step_deg": 45.0,
    "max_wait_seconds": 3.0,
    "max_total_steps": 50,
    "max_repeat_count": 3,
    "max_program_seconds": 30.0,
    "max_total_distance_cm": 300.0,
    "max_total_angle_deg": 900.0,
}

#: Champs que l'interface a le droit de régler, avec leur plafond.
ADJUSTABLE: dict[str, str] = {
    "max_linear_speed": "max_linear_speed",
    "max_angular_speed": "max_angular_speed",
    "max_distance_per_step_cm": "max_distance_per_step_cm",
    "max_angle_per_step_deg": "max_angle_per_step_deg",
    "max_wait_seconds": "max_wait_seconds",
    "max_total_steps": "max_total_steps",
    "max_repeat_count": "max_repeat_count",
    "max_program_seconds": "max_program_seconds",
    "max_total_distance_cm": "max_total_distance_cm",
    "max_total_angle_deg": "max_total_angle_deg",
}


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


class SettingsError(ValueError):
    """Un réglage est refusé. Le message est destiné à l'adulte."""


#: Plafonds effectifs : constantes de code, non modifiables par l'API.
HARD_CEILINGS = HardCeilings()


def _target_section(limits: Limits, field_name: str) -> object:
    """Retrouve l'objet qui porte le champ Adjustable."""
    if field_name in (
        "max_linear_speed",
        "max_angular_speed",
        "max_distance_per_step_cm",
        "max_angle_per_step_deg",
    ):
        return limits.motion
    if field_name == "max_wait_seconds":
        return limits.timing
    return limits.program


def adjustable_settings(limits: Limits) -> dict[str, float]:
    """Valeurs courantes des réglages, pour alimenter l'interface."""
    return {
        name: float(getattr(_target_section(limits, name), name))
        for name in ADJUSTABLE
    }


def apply_settings(limits: Limits, updates: dict[str, Any]) -> dict[str, float]:
    """Applique des réglages en vérifiant les planchers ET les plafonds.

    Un champ absent de `updates` est laissé tel quel : l'interface peut n'envoyer
    que ce qu'un adulte a modifié.

    Raises `SettingsError` si un champ est inconnu, non numérique, ou hors
    des bornes. Rien n'est modifié tant que la totalité n'a pas été validée.
    """
    ceilings = vars(HARD_CEILINGS)
    proposed: dict[str, float] = {}

    for name, value in updates.items():
        if name not in ADJUSTABLE:
            raise SettingsError(f"Le réglage « {name} » n’existe pas.")

        # bool est un sous-type de int : l'écarter explicitement.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SettingsError(f"Le réglage « {name} » doit être un nombre.")

        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise SettingsError(f"Le réglage « {name} » n’est pas un nombre valide.")

        floor = HARD_FLOORS[name]
        ceiling = ceilings[name]
        if not (floor <= number <= ceiling):
            raise SettingsError(
                f"« {name} » doit être compris entre {floor:g} et {ceiling:g}."
            )
        proposed[name] = number

    # Vérifications de cohérence entre réglages.
    max_distance = proposed.get(
        "max_distance_per_step_cm", limits.motion.max_distance_per_step_cm
    )
    max_steps = proposed.get("max_total_steps", float(limits.program.max_total_steps))
    max_distance_total = proposed.get(
        "max_total_distance_cm", limits.program.max_total_distance_cm
    )
    if max_distance_total < max_distance:
        raise SettingsError(
            "La distance totale doit être au moins égale à la distance d'un pas."
        )
    if max_distance_total > max_steps * max_distance:
        raise SettingsError(
            "La distance totale est trop grande pour le nombre de pas maximum."
        )

    angle_total = proposed.get(
        "max_total_angle_deg", limits.program.max_total_angle_deg
    )
    if angle_total < max_steps:
        # Sans ce garde-fou, une rotation unique pourrait dépasser le cumul.
        raise SettingsError(
            "La rotation totale doit être au moins égale au nombre de pas."
        )

    # Une seule attente ne doit pas pouvoir dépasser à elle seule toute la
    # durée autorisée : sinon le réglage de l'attente absorberait le budget.
    max_wait = proposed.get("max_wait_seconds", limits.timing.max_wait_seconds)
    program_seconds = proposed.get(
        "max_program_seconds", limits.program.max_program_seconds
    )
    if max_wait > program_seconds:
        raise SettingsError(
            "L’attente maximale doit être inférieure à la durée du programme."
        )

    # Rien n'est écrit tant que tout n'est pas valide.
    for name, number in proposed.items():
        setattr(_target_section(limits, name), name, number)

    return adjustable_settings(limits)