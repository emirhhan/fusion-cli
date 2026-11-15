"""Güvenilmeyen proje klasöründeki ajan dosyası izin kipini yükseltemez (inceleme #1)."""

from __future__ import annotations

import dataclasses

from fusion_cli.config import trust
from fusion_cli.engines.agent import team_settings
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.engines.agent.team import GENERIC_PERSONA
from tests.test_team_settings import _deps


def _project_persona(tmp_path):
    agent = tmp_path / ".claude" / "agents" / "helper.md"
    agent.parent.mkdir(parents=True)
    agent.write_text("---\nname: helper\ndescription: d\npermissionMode: acceptEdits\n---\nYardım")
    return dataclasses.replace(
        GENERIC_PERSONA,
        name="helper",
        permission_mode="acceptEdits",
        source="proje",
        definition_path=agent,
    )


def test_guvenilmeyen_proje_ajani_izin_kipini_yukseltemez(tmp_path, monkeypatch):
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    deps, built = _deps(tmp_path, mode=ApprovalMode.SECURITY)
    deps.home = tmp_path / "home"
    persona = _project_persona(tmp_path)

    team_settings.child_policies(deps, persona, "çocuk")
    reader = team_settings.child_approval_mode(deps, persona)
    main = team_settings.main_approval_mode(
        deps.config, persona, ApprovalMode.SECURITY, root=tmp_path, home=deps.home
    )

    assert ApprovalMode.ACCEPT_EDITS not in built
    assert reader is None or reader() is ApprovalMode.SECURITY
    assert main is ApprovalMode.SECURITY


def test_guvenilen_proje_ajani_izin_kipini_uygular(tmp_path, monkeypatch):
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    deps, built = _deps(tmp_path, mode=ApprovalMode.SECURITY)
    deps.home = tmp_path / "home"
    persona = _project_persona(tmp_path)
    trust.trust_project(tmp_path)

    team_settings.child_policies(deps, persona, "çocuk")
    reader = team_settings.child_approval_mode(deps, persona)

    assert built == [ApprovalMode.ACCEPT_EDITS]
    assert reader is not None and reader() is ApprovalMode.ACCEPT_EDITS
    assert (
        team_settings.main_approval_mode(
            deps.config, persona, ApprovalMode.SECURITY, root=tmp_path, home=deps.home
        )
        is ApprovalMode.ACCEPT_EDITS
    )


def test_guvenilmeyen_proje_ajani_kipi_yine_de_siklastirabilir(tmp_path, monkeypatch):
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    deps, built = _deps(tmp_path, mode=ApprovalMode.SECURITY)
    deps.home = tmp_path / "home"
    persona = dataclasses.replace(_project_persona(tmp_path), permission_mode="plan")

    team_settings.child_policies(deps, persona, "çocuk")

    assert built == [ApprovalMode.PLAN]
