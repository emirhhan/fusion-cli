"""Enum eşitliğinde JSON boolean ve sayı türleri birbirinin yerine geçmez."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.config.paths import capabilities_dir
from fusion_cli.tools.emulation import validate_arguments
from tests.test_skill_proposal_cli import _observe_variant
from tests.test_skill_proposal_cli import proposal_workspace as _workspace_fixture
from tests.test_verified_skill_public_flow import CASES, apply_proposal, seed_plan

proposal_workspace = _workspace_fixture


@pytest.mark.parametrize(
    "value, choice",
    [
        (1, True),
        (0, False),
        (True, 1),
        (False, 0),
        ([1], [True]),
        ({"deger": 1}, {"deger": True}),
        ({"deger": [False]}, {"deger": [0]}),
    ],
)
def test_enum_rejects_boolean_number_substitution(value: object, choice: object) -> None:
    schema = {"type": "object", "properties": {"deger": {"enum": [choice]}}}
    assert validate_arguments(schema, {"deger": value})


@pytest.mark.parametrize(
    "value, choice",
    [
        (1, 1.0),
        (-2.0, -2),
        (True, True),
        (False, False),
        (None, None),
        ([1, False], [1.0, False]),
        ({"deger": [-2, True]}, {"deger": [-2.0, True]}),
        ("1", "1"),
    ],
)
def test_enum_preserves_equal_json_values(value: object, choice: object) -> None:
    schema = {"type": "object", "properties": {"deger": {"enum": [choice]}}}
    assert validate_arguments(schema, {"deger": value}) == ()


@pytest.mark.parametrize(
    "kind,value,choice",
    [
        ("integer", 1, True),
        ("boolean", True, 1),
        ("object", {"deger": 1}, {"deger": True}),
        ("array", [False], [0]),
    ],
)
def test_public_apply_rejects_cross_type_enum(
    proposal_workspace: Path,
    kind: str,
    value: object,
    choice: object,
) -> None:
    proposal, _ = seed_plan(proposal_workspace, CASES[2])
    schema = {
        "type": "object",
        "properties": {"baslik": {"type": kind, "enum": [choice]}},
        "required": ["baslik"],
    }
    variant = _observe_variant(proposal, replace(proposal.routine, input_schema=json.dumps(schema)))
    result = apply_proposal(variant, {"baslik": value})
    assert result.exit_code == 1
    assert not capabilities_dir().exists()
