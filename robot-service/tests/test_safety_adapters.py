"""Adaptateur physique : ce qui doit rester INTERDIT tant que le robot n'a
pas été validé.

Ces tests sont la barrière la plus importante du projet. Tant que le Go2 Pro
n'a pas été piloté par un adulte, en présence d'un observateur, aucun test ne
doit pouvoir passer de la simulation au pilotage réel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from go2_service.adapters.unitree import UNITREE_CAPABILITIES  # noqa: E402
from go2_service.validation import Capability  # noqa: E402


class TestUnitreeIsDisabledByDefault:
    """Le mode réel doit être refusé par DÉFAUT.

    Pas « sauf si une variable d'environnement le demande » : ces tests
    échouent volontairement dès qu'on passe `physical_commands_enabled` à
    `True`. Les faire passer est l'une des étapes de la campagne de
    validation physique (docs/ROBOT_SETUP.md §5).
    """

    @pytest.fixture()
    def adapter(self):
        from go2_service.adapters.unitree import UnitreeAdapter
        from go2_service.config import load_limits

        return UnitreeAdapter(limits=load_limits(), network_interface="lo")

    def test_physical_commands_are_disabled(self, adapter):
        assert adapter.physical_commands_enabled is False

    @pytest.mark.asyncio
    async def test_connecting_is_refused_until_the_physical_campaign_is_done(self, adapter):
        # Refus dès la connexion, pas seulement à la première commande : rien
        # ne peut donc ouvrir une session physique par accident.
        from go2_service.adapters.unitree import UnitreeValidationError

        with pytest.raises(UnitreeValidationError, match="campagne physique"):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_a_movement_is_refused_while_disabled(self, adapter):
        from go2_service.adapters.base import AdapterError
        from go2_service.validation import CommandKind, RobotCommand

        command = RobotCommand(kind=CommandKind.MOVE_FORWARD, speed=0.2, duration_s=1)
        with pytest.raises((AdapterError, Exception)):
            await adapter.execute_command(command, 0, None)


class TestUnitreeCapabilities:
    """L'adaptateur ne revendique QUE ce que le SDK confirme."""

    def test_movement_posture_wait_and_stop_are_available(self):
        for capability in (
            Capability.MOVEMENT,
            Capability.POSTURE,
            Capability.WAIT,
            Capability.STOP,
        ):
            assert capability in UNITREE_CAPABILITIES

    def test_the_logic_of_the_plan_is_available(self):
        # Variables et messages ne commandent aucun organe : ils s'exécutent
        # dans le service, robot réel compris.
        assert Capability.VARIABLE in UNITREE_CAPABILITIES
        assert Capability.BROADCAST in UNITREE_CAPABILITIES

    def test_the_robot_state_is_readable(self):
        # Sujet `rt/sportmodestate`, type `SportModeState_` : lu et vérifié.
        assert Capability.SENSOR_STATE in UNITREE_CAPABILITIES

    def test_obstacle_detection_is_not_claimed(self):
        # ⚠️ Aucune mesure de distance n'a été identifiée dans l'API officielle
        # lue. Le revendiquer ferait afficher un nombre fabriqué sur un vrai
        # robot — c'est exactement ce qu'interdit le cahier des charges.
        assert Capability.SENSOR_OBSTACLE not in UNITREE_CAPABILITIES

    def test_every_capability_is_known(self):
        # Une capacité inventée passerait inaperçue dans un `frozenset`.
        for capability in UNITREE_CAPABILITIES:
            assert isinstance(capability, Capability)