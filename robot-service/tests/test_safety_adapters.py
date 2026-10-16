"""Tests de sécurité de l'adaptateur physique Unitree.

Ces tests ne pilotent AUCUN robot. Ils vérifient que l'adaptateur physique
refuse de fonctionner tant que la validation physique n'a pas eu lieu, et que
le code ne prétend pas davantage que ce qu'il sait.

C'est un garde-fou volontaire : si quelqu'un inverse `physical_commands_enabled`
sans avoir fait la campagne de `docs/ROBOT_SETUP.md`, ces tests le signalent.
"""

from __future__ import annotations

import inspect

import pytest

from go2_service.adapters.base import (
    AdapterError,
    Posture,
    RobotAdapter,
    RobotState,
    Status,
    StopSignal,
)
from go2_service.adapters.simulated import SimulatedAdapter
from go2_service.adapters.unitree import (
    TOPIC_HIGHSTATE,
    UNITREE_CAPABILITIES,
    UnitreeAdapter,
    UnitreeValidationError,
)
from go2_service.config import load_limits
from go2_service.validation import Capability, CommandKind, RobotCommand


@pytest.fixture
def limits():
    return load_limits()


class TestUnitreeIsDisabledByDefault:
    def test_physical_commands_are_disabled(self, limits):
        """Par défaut, l'adaptateur physique ne doit jamais piloter."""
        adapter = UnitreeAdapter(limits, "eth0")
        assert adapter.physical_commands_enabled is False

    def test_connect_is_refused(self, limits):
        import asyncio

        adapter = UnitreeAdapter(limits, "eth0")
        with pytest.raises(UnitreeValidationError):
            asyncio.run(adapter.connect())

    def test_execute_command_is_refused(self, limits):
        import asyncio

        adapter = UnitreeAdapter(limits, "eth0")
        adapter._connected = True
        adapter._client = object()  # volontairement invalide
        with pytest.raises(UnitreeValidationError):
            asyncio.run(
                adapter.execute_command(
                    RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=50),
                    0,
                    StopSignal(),
                )
            )

    def test_documents_its_unverified_items(self):
        """L'adaptateur doit continuer à declaring ce qui n'est pas vérifié."""
        assert len(UnitreeAdapter.UNVERIFIED) > 0
        for item in UnitreeAdapter.UNVERIFIED:
            assert isinstance(item, str) and item.strip()

    def test_topic_matches_official_example(self):
        """Constante TOPIC_HIGHSTATE de l'exemple officiel C++."""
        assert TOPIC_HIGHSTATE == "rt/sportmodestate"


class TestUnitreeInterfaceConforms:
    def test_satisfies_the_adapter_protocol(self, limits):
        adapter = UnitreeAdapter(limits, "eth0")
        assert isinstance(adapter, RobotAdapter)

    def test_simulated_also_satisfies_the_protocol(self, limits):
        adapter = SimulatedAdapter(limits)
        assert isinstance(adapter, RobotAdapter)

    def test_both_expose_the_same_contract(self, limits):
        """Le moteur ne doit pas dépendre d'un adaptateur particulier."""
        sim = SimulatedAdapter(limits)
        unit = UnitreeAdapter(limits, "eth0")
        for name in ("connect", "disconnect", "get_status", "execute_command", "request_stop"):
            assert callable(getattr(sim, name)), name
            assert callable(getattr(unit, name)), name

    def test_simulated_is_never_physical(self, limits):
        assert SimulatedAdapter(limits).physical_commands_enabled is False

    def test_capabilities_are_named_not_invented(self):
        """Seules les quatre capacités du projet, rien de plus."""
        assert UNITREE_CAPABILITIES == frozenset(
            {Capability.MOVEMENT, Capability.POSTURE, Capability.WAIT, Capability.STOP}
        )

    def test_no_low_level_motor_control(self):
        """Aucune commande basse niveau ne doit exister dans le projet.

        Le contrôle porte sur les IDENTIFIANTS du code (noms, attributs,
        paramètres). Commentaires et chaînes de caractères sont ignorés : le
        fichier documente nommément l'absence de `rt/lowcmd`, et cette mention
        ne doit pas être confondue avec une implémentation.
        """
        import ast
        import go2_service.adapters.unitree as module

        tree = ast.parse(inspect.getsource(module))

        identifiers: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                identifiers.append(node.attr)
            elif isinstance(node, ast.Name):
                identifiers.append(node.id)
            elif isinstance(node, ast.arg):
                identifiers.append(node.arg)
            elif isinstance(node, ast.keyword) and node.arg:
                identifiers.append(node.arg)

        code = " ".join(identifiers).lower()
        for forbidden in ("lowcmd", "lowstate", "crc32", "motor_cmd", "pos_stop_f"):
            assert forbidden not in code, f"référence interdite : {forbidden}"

    def test_simulated_never_mentions_the_sdk(self):
        """Le simulateur ne doit jamais toucher au SDK."""
        import ast
        import go2_service.adapters.simulated as module

        tree = ast.parse(inspect.getsource(module))
        identifiers: list[str] = [
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if isinstance(node, (ast.Attribute, ast.Name))
        ]
        assert "unitree" not in " ".join(identifiers).lower()


class TestUnknownCommandsAreRefused:
    """Une commande non gérée doit être refusée, jamais improvisée."""

    async def test_simulated_refuses_disconnect(self, limits):
        adapter = SimulatedAdapter(limits)
        with pytest.raises(AdapterError):
            await adapter.execute_command(
                RobotCommand(kind=CommandKind.MOVE_FORWARD, distance_cm=50),
                0,
                StopSignal(),
            )

    async def test_simulated_supports_only_declared_capabilities(self, limits):
        adapter = SimulatedAdapter(limits)
        assert adapter.supports(Capability.MOVEMENT)
        assert adapter.supports(Capability.STOP)
        # Une capacité inconnue n'est jamais « supportée » par défaut.
        assert not adapter.supports("unsupported")  # type: ignore[arg-type]

    async def test_status_never_raises(self, limits):
        """`get_status` doit toujours répondre, même déconnecté."""
        adapter = SimulatedAdapter(limits)
        status = await adapter.get_status()
        assert isinstance(status, Status)
        assert status.state is RobotState.DISCONNECTED
        assert status.connected is False
        assert status.blocked_reason is not None


class TestPostureHonesty:
    """Une posture ne doit jamais être présentée comme mesurée."""

    async def test_simulated_posture_reports_no_measurement(self, limits):
        adapter = SimulatedAdapter(limits)
        await adapter.connect()
        outcome = await adapter.execute_command(
            RobotCommand(kind=CommandKind.STAND_UP), 0, StopSignal()
        )
        assert outcome.measured_distance_cm is None
        assert outcome.measured_angle_deg is None
        assert outcome.detail is not None

    def test_posture_enum_is_limited(self):
        """Seules deux postures, toutes deux vérifiées."""
        assert {p.value for p in Posture} == {"stand", "sit"}