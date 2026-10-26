"""Géométrie du contrôle d'obstacles : couloir, sol, directions, seuils.

Aucun robot n'est nécessaire : on donne une carte et une pose, on vérifie la
distance libre annoncée et la décision qui en découle.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.obstacles import (  # noqa: E402
    BODY_CLEARANCE_M,
    CORRIDOR_HALF_WIDTH_M,
    SIDE_CLEARANCE_M,
    SIDE_CORRIDOR_HALF_WIDTH_M,
    TRAVEL_MARGIN_M,
    body_clearance_m,
    corridor_half_width_m,
    direction_of,
    free_distance_m,
    motion_direction,
    obstacle_cells,
    obstacle_message,
    obstacle_stop_message,
    required_clearance_m,
    travel_distance_m,
)
from go2_service.validation import CommandKind, RobotCommand  # noqa: E402


class TestObstacleCells:
    def test_the_floor_and_the_ceiling_are_ignored(self):
        # Grille de 5 cm, sol à z = 0. Le mur monte de 0 à 2 m.
        cases = {(ix, iy, 0) for ix in range(5) for iy in range(5)}
        cases.add((20, 0, 10))  # mur à 1 m, z = 0,50 m
        cases.add((0, 0, 50))  # plafond à 2,50 m
        cases.add((5, 5, 2))  # objet bas à 0,10 m

        cellules = obstacle_cells(cases, (0.0, 0.0, 0.0), 0.05)

        assert (1.0, 0.0) in cellules
        assert (0.0, 0.0) not in cellules  # sol
        assert (0.0, 0.0) not in cellules  # plafond, même colonne
        assert (0.25, 0.25) not in cellules  # objet sous 0,25 m

    def test_an_empty_map_gives_no_obstacle(self):
        assert obstacle_cells([], (0.0, 0.0, 0.0), 0.05) == []

    def test_a_zero_resolution_is_refused(self):
        assert obstacle_cells({(0, 0, 0)}, (0.0, 0.0, 0.0), 0.0) == []

    def test_height_is_measured_from_the_floor(self):
        # Le sol n'est pas à z = 0 dans ce repère : il est à -0,50 m.
        cases = {(-10, iy, -10) for iy in range(20)}  # sol à -0,50 m
        cases.add((20, 0, -9))  # 5 cm au-dessus du sol : ignoré
        cases.add((20, 0, -1))  # 45 cm au-dessus du sol : mur

        cellules = obstacle_cells(cases, (0.0, 0.0, 0.0), 0.05)

        assert (1.0, 0.0) in cellules
        assert (-0.5, -0.5) not in cellules
        assert (-0.5, 0.0) not in cellules

    def test_a_voxel_below_the_floor_does_not_turn_the_floor_into_a_wall(self):
        # Le sol est à z = 0 ; un unique voxel aberrant est à -0,30 m.
        # Avec un minimum, le seuil descendrait à -0,05 m et tout le sol
        # entrerait dans les obstacles.
        cases = {(ix, iy, 0) for ix in range(10) for iy in range(10)}
        cases.add((0, 0, -6))  # voxel aberrant à -0,30 m
        cases.add((20, 0, 10))  # mur à 0,50 m

        cellules = obstacle_cells(cases, (0.0, 0.0, 0.0), 0.05)

        assert (1.0, 0.0) in cellules
        assert (0.0, 0.0) not in cellules
        assert (0.1, 0.0) not in cellules
        assert (0.4, 0.4) not in cellules

    def test_a_thick_floor_stays_floor(self):
        # Le sol cartographié occupe deux couches (0 et 0,25 m). La couche
        # haute est exactement à la limite d'un filtre basé sur le minimum :
        # elle doit pourtant rester du sol.
        cases = {(ix, iy, 0) for ix in range(10) for iy in range(10)}
        cases.update({(ix, iy, 5) for ix in range(10) for iy in range(10)})
        cases.add((20, 0, 15))  # mur à 0,75 m

        cellules = obstacle_cells(cases, (0.0, 0.0, 0.0), 0.05)

        assert (1.0, 0.0) in cellules
        assert (0.0, 0.0) not in cellules
        assert (0.4, 0.4) not in cellules
        # La couche haute du sol ne doit pas devenir un mur.
        assert (0.0, 0.25) not in cellules


class TestFreeDistance:
    def test_a_wall_straight_ahead(self):
        libre = free_distance_m([(1.0, 0.0)], (0.0, 0.0), 0.0, "forward")
        # Le point est le centre d'une case de 5 cm : on retire une case.
        assert libre == pytest.approx(0.95)

    def test_a_wall_just_inside_the_corridor(self):
        y = CORRIDOR_HALF_WIDTH_M - 0.01
        libre = free_distance_m([(1.0, y)], (0.0, 0.0), 0.0, "forward")
        assert libre == pytest.approx(0.95)

    def test_a_wall_outside_the_corridor_does_not_count(self):
        y = CORRIDOR_HALF_WIDTH_M + 0.01
        libre = free_distance_m([(1.0, y)], (0.0, 0.0), 0.0, "forward")
        assert math.isinf(libre)

    def test_a_side_step_uses_a_wider_corridor(self):
        # Le corps est en travers : le couloir latéral doit couvrir sa
        # longueur (0,70 m), pas seulement sa largeur. Ici le mur est à 1 m
        # sur le côté, à 0,44 m de l'axe du pas.
        x = SIDE_CORRIDOR_HALF_WIDTH_M - 0.01
        assert free_distance_m(
            [(x, 1.0)], (0.0, 0.0), 0.0, "left"
        ) == pytest.approx(0.95)
        x = SIDE_CORRIDOR_HALF_WIDTH_M + 0.01
        assert math.isinf(
            free_distance_m([(x, 1.0)], (0.0, 0.0), 0.0, "left")
        )

    def test_no_cell_at_all_is_not_a_wall(self):
        assert math.isinf(free_distance_m([], (0.0, 0.0), 0.0, "forward"))

    def test_the_nearest_cell_wins(self):
        libre = free_distance_m(
            [(2.0, 0.0), (1.0, 0.0)], (0.0, 0.0), 0.0, "forward"
        )
        assert libre == pytest.approx(0.95)

    def test_the_heading_turns_the_forward_direction(self):
        # Cap 90° : le museau pointe vers +Y.
        libre = free_distance_m(
            [(0.0, 1.0)], (0.0, 0.0), math.pi / 2.0, "forward"
        )
        assert libre == pytest.approx(0.95)

    def test_a_cell_behind_is_ignored_when_going_forward(self):
        libre = free_distance_m([(-1.0, 0.0)], (0.0, 0.0), 0.0, "forward")
        assert math.isinf(libre)

    def test_backward_looks_behind(self):
        libre = free_distance_m([(-1.0, 0.0)], (0.0, 0.0), 0.0, "backward")
        assert libre == pytest.approx(0.95)
        assert math.isinf(
            free_distance_m([(1.0, 0.0)], (0.0, 0.0), 0.0, "backward")
        )

    def test_left_and_right_use_the_side_of_the_robot(self):
        # Cap 0 : +Y est à gauche du chien.
        gauche = free_distance_m([(0.0, 1.0)], (0.0, 0.0), 0.0, "left")
        droite = free_distance_m([(0.0, -1.0)], (0.0, 0.0), 0.0, "right")
        assert gauche == pytest.approx(0.95)
        assert droite == pytest.approx(0.95)

    def test_the_robot_position_is_subtracted(self):
        libre = free_distance_m([(3.0, 2.0)], (2.0, 2.0), 0.0, "forward")
        assert libre == pytest.approx(0.95)

    def test_the_corridor_is_centred_on_the_travel_direction(self):
        # Cap 90°, un mur à gauche du déplacement (vers -X) est hors couloir.
        libre = free_distance_m(
            [(0.0, 1.0)], (0.0, 0.0), math.pi / 2.0, "forward"
        )
        assert libre == pytest.approx(0.95)
        assert math.isinf(
            free_distance_m(
                [(-0.5, 1.0)], (0.0, 0.0), math.pi / 2.0, "forward"
            )
        )

    def test_an_unknown_direction_is_an_error(self):
        with pytest.raises(ValueError):
            free_distance_m([], (0.0, 0.0), 0.0, "up")


class TestClearanceDecision:
    def test_required_distance_grows_with_the_move(self):
        assert required_clearance_m(0.0) == pytest.approx(
            BODY_CLEARANCE_M + TRAVEL_MARGIN_M
        )
        assert required_clearance_m(0.3) == pytest.approx(0.75)
        assert required_clearance_m(1.5) == pytest.approx(1.95)

    def test_a_wall_one_metre_away_allows_one_second_but_not_five(self):
        # À 0,30 m/s : 1 s = 0,30 m (il faut 0,75 m), 5 s = 1,50 m (1,95 m).
        libre = 1.0
        assert libre >= required_clearance_m(0.30)
        assert libre < required_clearance_m(1.50)

    def test_travel_distance_uses_speed_and_duration(self):
        commande = RobotCommand(
            kind=CommandKind.MOVE_FORWARD, speed=0.30, duration_s=5.0
        )
        assert travel_distance_m(commande) == pytest.approx(1.5)

    def test_a_side_step_needs_less_body_clearance_but_a_wider_corridor(self):
        # Un pas latéral engage la largeur du chien (0,25 m avec la marge),
        # mais son corps occupe toute la longueur du couloir (0,45 m).
        assert body_clearance_m("left") == pytest.approx(SIDE_CLEARANCE_M)
        assert body_clearance_m("right") == pytest.approx(SIDE_CLEARANCE_M)
        assert body_clearance_m("forward") == pytest.approx(BODY_CLEARANCE_M)
        assert body_clearance_m("backward") == pytest.approx(BODY_CLEARANCE_M)
        assert corridor_half_width_m("left") == pytest.approx(
            SIDE_CORRIDOR_HALF_WIDTH_M
        )
        assert corridor_half_width_m("forward") == pytest.approx(
            CORRIDOR_HALF_WIDTH_M
        )

    def test_a_side_step_requires_body_plus_travel_plus_margin(self):
        assert required_clearance_m(0.3, "left") == pytest.approx(0.60)
        assert required_clearance_m(0.3, "right") == pytest.approx(0.60)
        assert required_clearance_m(0.3, "forward") == pytest.approx(0.75)

    def test_a_backward_move_uses_the_same_distance(self):
        commande = RobotCommand(
            kind=CommandKind.MOVE_BACKWARD, speed=0.30, duration_s=2.0
        )
        assert travel_distance_m(commande) == pytest.approx(0.6)


class TestDirectionNames:
    def test_each_translation_has_its_direction(self):
        assert direction_of(CommandKind.MOVE_FORWARD) == "forward"
        assert direction_of(CommandKind.MOVE_BACKWARD) == "backward"
        assert direction_of(CommandKind.MOVE_LEFT) == "left"
        assert direction_of(CommandKind.MOVE_RIGHT) == "right"

    def test_other_commands_have_no_translation_direction(self):
        assert direction_of(CommandKind.TURN_LEFT) is None
        assert direction_of(CommandKind.WAIT) is None
        assert direction_of(CommandKind.STOP) is None

    def test_motion_direction_follows_the_speed_signs(self):
        assert motion_direction(0.3, 0.0) == "forward"
        assert motion_direction(-0.3, 0.0) == "backward"
        assert motion_direction(0.0, 0.3) == "left"
        assert motion_direction(0.0, -0.3) == "right"
        assert motion_direction(0.0, 0.0) is None


class TestMessages:
    def test_a_blocked_action_says_where_and_how_much_room_is_left(self):
        message = obstacle_message("forward", 0.5)
        assert "devant" in message
        assert "0,5 m" in message

    def test_the_message_is_in_french_with_a_comma(self):
        assert obstacle_message("backward", 1.25) == (
            "Pas assez de place derrière : il reste 1,2 m libres."
        )

    def test_a_move_stopped_in_progress_says_so(self):
        assert "arrêté" in obstacle_stop_message("left")
        assert "gauche" in obstacle_stop_message("left")
