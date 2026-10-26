"""Détection d'obstacles à partir de la carte du lidar.

Le lidar du Go2 construit une carte de voxels dans un repère « odom » (celui
de la carte, pas celui du robot). La pose du robot dans ce même repère est
publiée par le service de cartographie. Ce module transforme les cases
occupées en une distance libre dans la direction du déplacement.

Trois idées simples, et aucune invention :

  * le SOL est cartographié lui aussi : on ignore tout ce qui est à moins de
    25 cm au-dessus du niveau du sol. Ce niveau est estimé par la médiane
    des hauteurs, et non par la case la plus basse : le sol s'étale sur
    plusieurs couches, et ses points bas suffisent à faire passer son dessus
    pour un mur. Le chien mesure environ 32 cm de haut ; un obstacle plus
    bas que 25 cm est franchissable ou sans danger pour la coque ;
  * on ne regarde que le COULOIR que le robot va parcourir : sa largeur plus
    une marge, pour ne pas s'arrêter à cause d'une chaise deux mètres à côté ;
  * la distance retenue est celle de la case la PLUS PROCHE devant (ou
    derrière, ou sur le côté), moins une case : le point représenté est le
    centre d'un voxel de 5 cm.

Ce module ne décide pas : il rend une distance. La décision (« assez de
place ou pas ») est prise par le moteur d'exécution avant l'action, et par
l'adaptateur WebRTC pendant le déplacement.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import median

from .validation import CommandKind, RobotCommand

#: Demi-largeur du couloir regardé pour un pas avant ou arrière, en mètres.
#:
#: Le Go2 mesure 0,31 m de large : 0,155 m de demi-largeur, plus 0,145 m de
#: marge pour ne pas frôler un coin de mur.
CORRIDOR_HALF_WIDTH_M = 0.30

#: Demi-longueur du couloir pour un pas latéral, en mètres.
#:
#: Quand le chien glisse sur le côté, son corps est EN TRAVERS du couloir :
#: il faut couvrir ses 0,70 m de long, plus une marge.
SIDE_CORRIDOR_HALF_WIDTH_M = 0.45

#: Distance entre le centre du robot et son avant, plus une marge d'arrêt.
#:
#: Le chien mesure 0,70 m de long : 0,35 m du centre au museau, plus 0,05 m
#: pour ne jamais s'arrêter au contact.
BODY_CLEARANCE_M = 0.40

#: Distance entre le centre et le flanc, plus une marge, pour un pas latéral.
#:
#: Le chien mesure 0,31 m de large : 0,155 m, plus 0,095 m de marge.
SIDE_CLEARANCE_M = 0.25

#: Marge ajoutée à la distance que le robot va parcourir.
#:
#: Elle absorbe l'imprécision de la carte (cases de 5 cm, arrondis) et le
#: temps de réaction du chien. Réduite de 10 à 5 cm après les essais réels du
#: 22/10/2026 : elle reste volontairement égale à une case de la carte.
TRAVEL_MARGIN_M = 0.05

#: Marge retirée au point le plus proche, en mètres.
#:
#: Les positions sont des **centres** de voxels de 5 cm : on retire une case
#: entière pour ne jamais viser le centre, et parce que la carte elle-même
#: avance par pas de 5 cm. C'est volontairement conservateur.
CELL_MARGIN_M = 0.05

#: Hauteur minimale au-dessus du sol pour retenir une case, en mètres.
#:
#: Le sol est cartographié : sans ce filtre, toutes les directions seraient
#: « bloquées » par le plancher. Les pattes du robot sont plus basses.
OBSTACLE_HEIGHT_MIN_M = 0.25

#: Hauteur maximale retenue, en mètres. Au-delà, c'est le plafond.
OBSTACLE_HEIGHT_MAX_M = 1.60

#: Directions acceptées, dans le repère du robot.
DIRECTIONS = ("forward", "backward", "left", "right")

_LABELS = {
    "forward": "devant",
    "backward": "derrière",
    "left": "à gauche",
    "right": "à droite",
}


def direction_of(kind: CommandKind) -> str | None:
    """Direction d'un déplacement, ou `None` si ce n'est pas une translation."""
    return {
        CommandKind.MOVE_FORWARD: "forward",
        CommandKind.MOVE_BACKWARD: "backward",
        CommandKind.MOVE_LEFT: "left",
        CommandKind.MOVE_RIGHT: "right",
    }.get(kind)


def motion_direction(linear_mps: float, lateral_mps: float) -> str | None:
    """Direction d'un plan de mouvement déjà calculé.

    `Move(vx, vy, vyaw)` : `vx` positif avance, `vy` positif va à gauche.
    Une vitesse nulle ne demande aucun contrôle.
    """
    if linear_mps > 0.0:
        return "forward"
    if linear_mps < 0.0:
        return "backward"
    if lateral_mps > 0.0:
        return "left"
    if lateral_mps < 0.0:
        return "right"
    return None


def travel_distance_m(command: RobotCommand) -> float:
    """Distance que le robot va parcourir, à partir de sa vitesse et durée."""
    return abs(command.speed) * command.duration_s


def required_clearance_m(travel_m: float, direction: str = "forward") -> float:
    """Distance libre nécessaire pour faire ce déplacement sans toucher.

    C'est la longueur du robot dans le sens du pas, plus la distance
    parcourue, plus une marge d'arrêt. Un pas latéral engage la largeur du
    chien, pas sa longueur.
    """
    return body_clearance_m(direction) + max(0.0, travel_m) + TRAVEL_MARGIN_M


def body_clearance_m(direction: str) -> float:
    """Distance entre le centre du robot et son bord, dans le sens du pas."""
    if direction not in DIRECTIONS:
        raise ValueError(f"Direction inconnue : {direction}")
    return SIDE_CLEARANCE_M if direction in ("left", "right") else BODY_CLEARANCE_M


def corridor_half_width_m(direction: str) -> float:
    """Demi-largeur du couloir à balayer, selon le sens du pas."""
    if direction not in DIRECTIONS:
        raise ValueError(f"Direction inconnue : {direction}")
    return (
        SIDE_CORRIDOR_HALF_WIDTH_M
        if direction in ("left", "right")
        else CORRIDOR_HALF_WIDTH_M
    )


def obstacle_cells(
    cases: Iterable[tuple[int, int, int]],
    origin: tuple[float, float, float],
    resolution: float,
) -> list[tuple[float, float]]:
    """Cases occupées au-dessus du sol, vues du dessus, en mètres.

    `cases` sont les indices de voxels occupés, `origin` le coin de la grille
    et `resolution` le pas (0,05 m). Le niveau du sol est estimé par la
    médiane des hauteurs, pour ne pas dépendre d'un point bas isolé. Les
    cases du sol et du plafond sont ensuite écartées : voir
    `OBSTACLE_HEIGHT_MIN_M` et `OBSTACLE_HEIGHT_MAX_M`.
    """
    if resolution <= 0.0:
        return []
    cases = list(cases)
    ox, oy, oz = origin
    hauteurs = [oz + case[2] * resolution for case in cases]
    if not hauteurs:
        return []
    # Le sol est la surface dominante, mais il s'étale sur plusieurs
    # couches : bruit du lidar, inclinaison du robot, voxels aberrants.
    # Le minimum ou un percentile bas prennent le dessous du sol et
    # laissent passer son dessus pour un mur. La médiane donne le niveau
    # du sol ; le filtre de 25 cm écarte ensuite les couches basses.
    sol = median(hauteurs)
    bas = sol + OBSTACLE_HEIGHT_MIN_M
    haut = sol + OBSTACLE_HEIGHT_MAX_M

    cellules: set[tuple[float, float]] = set()
    for ix, iy, iz in cases:
        z = oz + iz * resolution
        if z < bas or z > haut:
            continue
        cellules.add((round(ox + ix * resolution, 3), round(oy + iy * resolution, 3)))
    return sorted(cellules)


def free_distance_m(
    cells: Iterable[tuple[float, float]],
    robot_xy: tuple[float, float],
    cap_rad: float,
    direction: str,
) -> float:
    """Distance libre dans une direction, en mètres.

    Le robot est au point `robot_xy`, son museau pointe vers `cap_rad` (le
    cap de la carte). `direction` est une des `DIRECTIONS`.

    Renvoie `math.inf` quand aucune case n'est dans le couloir : la carte ne
    montre rien, elle ne prouve pas qu'il y a un mur.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"Direction inconnue : {direction}")

    cos_cap = math.cos(cap_rad)
    sin_cap = math.sin(cap_rad)
    # Vecteur unitaire du déplacement, dans le repère de la carte.
    if direction == "forward":
        ux, uy = cos_cap, sin_cap
    elif direction == "backward":
        ux, uy = -cos_cap, -sin_cap
    elif direction == "left":
        ux, uy = -sin_cap, cos_cap
    else:  # right
        ux, uy = sin_cap, -cos_cap

    rx, ry = robot_xy
    demi_largeur = corridor_half_width_m(direction)
    plus_proche = math.inf
    for x, y in cells:
        dx = x - rx
        dy = y - ry
        longitudinal = dx * ux + dy * uy
        if longitudinal <= 0.0:
            continue
        lateral = -dx * uy + dy * ux
        if abs(lateral) > demi_largeur:
            continue
        if longitudinal < plus_proche:
            plus_proche = longitudinal

    if math.isinf(plus_proche):
        return math.inf
    return max(0.0, plus_proche - CELL_MARGIN_M)


def obstacle_message(direction: str, free_m: float) -> str:
    """Phrase expliquant pourquoi l'action n'est pas faite."""
    where = _LABELS[direction]
    if math.isinf(free_m):
        return f"Pas assez de place {where} : je ne fais pas cette action."
    distance = f"{free_m:.1f}".replace(".", ",")
    return f"Pas assez de place {where} : il reste {distance} m libres."


def obstacle_stop_message(direction: str) -> str:
    """Phrase expliquant un arrêt en cours de déplacement."""
    return (
        f"Un obstacle est trop proche {_LABELS[direction]} : "
        "je me suis arrêté."
    )
