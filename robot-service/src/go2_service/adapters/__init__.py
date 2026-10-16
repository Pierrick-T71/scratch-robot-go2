"""Adaptateurs de robot.

`base` définit le contrat interne. `simulated` est le simulateur de
développement. `unitree` est l'adaptateur physique, volontairement
DÉSACTIVÉ tant que la validation physique n'a pas eu lieu.
"""

from .base import (
    AdapterError,
    CommandOutcome,
    MotionPlan,
    Posture,
    RobotAdapter,
    RobotState,
    Status,
    StopSignal,
)
from .simulated import SimulatedAdapter

__all__ = [
    "AdapterError",
    "CommandOutcome",
    "MotionPlan",
    "Posture",
    "RobotAdapter",
    "RobotState",
    "SimulatedAdapter",
    "Status",
    "StopSignal",
]