"""Adaptateurs de robot.

`base` définit le contrat interne. `simulated` est le simulateur de
développement. `unitree` est l'adaptateur DDS officiel : il reste écrit,
mais inutilisable sur ce robot, dont l'interface réseau n'expose aucun
participant DDS (sondes unicast négatives sur les domaines 0 à 3).
`webrtc` est l'adaptateur retenu : il passe par le canal de l'application
mobile, seul chemin de commande réellement disponible.
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