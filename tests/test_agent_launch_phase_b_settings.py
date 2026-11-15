"""Ajan başlatma ayarlarının tek tipli ve geriye uyumlu yüklenmesi."""

from __future__ import annotations

import dataclasses
import logging

import pytest
import yaml

from fusion_cli.config import loader
from fusion_cli.config.paths import bundled_defaults
from fusion_cli.core.errors import ConfigError


def test_eski_yapilandirma_yeni_ajan_ayarlarini_bos_olarak_alir():
    raw = yaml.safe_load(bundled_defaults().read_text())
    config = loader._assemble(raw, None)
    assert hasattr(config, "agent_launch")
    assert config.agent_launch.subagent_model == ""
    assert config.agent_launch.force_subagent_model is False
    assert config.agent_launch.available_models is None
    assert dataclasses.is_dataclass(config.agent_launch)


def test_ajan_ayarlari_defaults_ile_birebir_eslesir():
    raw = yaml.safe_load(bundled_defaults().read_text())
    assert "agent_launch" in raw
    config = loader._assemble(raw, None)
    assert dataclasses.asdict(config.agent_launch) == {
        **raw["agent_launch"],
        "model_aliases": (),
        "auto_supported_models": (),
        "managed_agent_roots": (),
    }


def test_claude_ortam_ayarlari_yalniz_config_yuklenirken_okunur(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "load_environment", lambda: None)
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "haiku")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", "1")
    monkeypatch.setenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "sahte/haiku")
    path = tmp_path / "config.yaml"
    path.write_text("agent_launch:\n  disable_auto_mode: true\n")
    config = loader.load_config(path)
    assert hasattr(config, "agent_launch")
    assert config.agent_launch.subagent_model == "haiku"
    assert config.agent_launch.force_subagent_model
    assert ("haiku", "sahte/haiku") in config.agent_launch.model_aliases
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "opus")
    assert config.agent_launch.subagent_model == "haiku"
    assert config.agent_launch.disable_auto_mode


def test_claude_ayar_dosyasi_birincil_ad_olarak_uyarisiz_okunur(tmp_path, caplog):
    from fusion_cli.config.agent_launch_compat import read_agent_launch
    from fusion_cli.config.agent_launch_settings import AgentLaunchConfig

    home = tmp_path / "home"
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"agent":"denetci","availableModels":["haiku"],"env":{"CLAUDE_CODE_SUBAGENT_MODEL":"haiku"}}'
    )
    with caplog.at_level(logging.WARNING):
        loaded = read_agent_launch(AgentLaunchConfig(), home=home, root=tmp_path, environ={})
    assert loaded.default_agent == "denetci"
    assert loaded.available_models == ("haiku",)
    assert loaded.subagent_model == "haiku"
    # Claude ayar adları birincildir; okunmaları kullanımdan kalkma uyarısı üretmez (#15).
    assert not any("uyumluluk" in record.message for record in caplog.records)


def test_bilinmeyen_ajan_ayari_acik_hata_verir():
    raw = yaml.safe_load(bundled_defaults().read_text())
    raw["agent_launch"] = {"uydurma": True}
    with pytest.raises(ConfigError, match="uydurma"):
        loader._assemble(raw, None)


def test_mevcut_guven_komutu_ajan_dosyasini_icerigiyle_onaylar_degisiklikte_iptal_eder(
    tmp_path, monkeypatch
):
    from fusion_cli.config import trust

    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    root = tmp_path / "project"
    agent = root / ".claude" / "agents" / "nested" / "denetci.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text('name = "denetci"\nprompt = "İncele"\n')
    trust.trust_project(root)
    assert trust.is_file_trusted(root, agent)
    agent.write_text('name = "denetci"\nprompt = "Değişti"\n')
    assert not trust.is_file_trusted(root, agent)
    outside = tmp_path / "outside.md"
    outside.write_text("Dışarıda")
    link = agent.with_name("link.md")
    link.symlink_to(outside)
    trust.trust_project(root)
    assert not trust.is_file_trusted(root, link)


def test_arka_plan_ve_fork_ortami_tipli_yapilandirmaya_bir_kez_alinir(tmp_path):
    from fusion_cli.config.agent_launch_compat import read_agent_launch
    from fusion_cli.config.agent_launch_settings import AgentLaunchConfig

    loaded = read_agent_launch(
        AgentLaunchConfig(),
        home=tmp_path / "home",
        root=tmp_path,
        environ={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "CLAUDE_CODE_FORK_SUBAGENT": "0"},
    )
    assert hasattr(loaded, "fork_enabled")
    assert loaded.disable_background_tasks is True
    assert loaded.fork_enabled is False
    assert AgentLaunchConfig().fork_enabled is True


def test_ajan_kaynak_guveni_gercek_kok_ve_dosya_izi_gerektirir(tmp_path, monkeypatch):
    from fusion_cli.config import trust
    from fusion_cli.engines.agent import team_settings
    from fusion_cli.engines.agent.team import GENERIC_PERSONA
    from tests.fakes import make_config

    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    home = tmp_path / "home"
    root = tmp_path / "project"
    project_agent = root / ".claude" / "agents" / "denetci.md"
    project_agent.parent.mkdir(parents=True)
    project_agent.write_text("Ajan")
    user_agent = home / ".claude" / "agents" / "denetci.md"
    user_agent.parent.mkdir(parents=True)
    user_agent.write_text("Kullanıcı")
    config = make_config(memory_dir=tmp_path / "memory")
    assert hasattr(team_settings, "is_trusted_agent_definition")
    check = team_settings.is_trusted_agent_definition
    project = dataclasses.replace(GENERIC_PERSONA, source="proje", definition_path=project_agent)
    assert not check(config, project, root=root, home=home)
    trust.trust_project(root)
    assert check(config, project, root=root, home=home)
    composite = dataclasses.replace(project, source="proje+ek-kok")
    assert check(config, composite, root=root, home=home)
    assert not check(
        config, dataclasses.replace(composite, source="proje+uydurma"), root=root, home=home
    )
    assert not check(config, project, root=root, home=None)
    project_agent.write_text("Değişti")
    assert not check(config, project, root=root, home=home)
    forged = dataclasses.replace(project, source="claude")
    assert not check(config, forged, root=root, home=home)
    user = dataclasses.replace(project, source="claude", definition_path=user_agent)
    assert check(config, user, root=root, home=home)
    assert not check(config, user, root=root, home=None)
    outside = tmp_path / "outside.md"
    outside.write_text("Dışarıda")
    user_agent.unlink()
    user_agent.symlink_to(outside)
    assert not check(config, user, root=root, home=home)


def test_cli_ve_yonetilen_ajan_guveni_sahte_kaynak_etiketiyle_acilmaz(tmp_path):
    from fusion_cli.engines.agent import team_settings
    from fusion_cli.engines.agent.team import GENERIC_PERSONA, resolve_persona
    from fusion_cli.tools.agent_catalog_launch import session_agents_from_json
    from fusion_cli.tools.capabilities import CapabilityRegistry
    from tests.fakes import make_config

    config = make_config(memory_dir=tmp_path / "memory")
    entries = session_agents_from_json(
        '{"denetci":{"prompt":"İncele","description":"d"}}', root=tmp_path
    )
    persona = resolve_persona(
        CapabilityRegistry(tmp_path / "home", tmp_path, session_agents=entries), "denetci"
    )
    check = team_settings.is_trusted_agent_definition
    assert check(config, persona, root=tmp_path)
    forged = dataclasses.replace(persona, definition_path=tmp_path / "foreign.md")
    assert not check(config, forged, root=tmp_path)
    managed = tmp_path / "managed"
    managed.mkdir()
    path = managed / "denetci.md"
    path.write_text("Yönetilen")
    persona = dataclasses.replace(GENERIC_PERSONA, source="managed", definition_path=path)
    assert not check(config, persona, root=tmp_path)
    configured = dataclasses.replace(
        config,
        agent_launch=dataclasses.replace(config.agent_launch, managed_agent_roots=(str(managed),)),
    )
    assert check(configured, persona, root=tmp_path)
    moved = path.with_name("moved.md")
    path.rename(moved)
    assert not check(configured, persona, root=tmp_path)


def test_guvenilen_claude_model_listeleri_birlesir_yapilandirilmis_liste_ustundur(
    tmp_path, monkeypatch
):
    from fusion_cli.config import trust
    from fusion_cli.config.agent_launch_compat import read_agent_launch
    from fusion_cli.config.agent_launch_settings import AgentLaunchConfig

    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "trust.json")
    home, root = tmp_path / "home", tmp_path / "project"
    user = home / ".claude" / "settings.json"
    user.parent.mkdir(parents=True)
    user.write_text('{"availableModels":["haiku"]}')
    project = root / ".claude" / "settings.json"
    project.parent.mkdir(parents=True)
    project.write_text('{"availableModels":["sonnet"]}')
    trust.trust_project(root)
    loaded = read_agent_launch(AgentLaunchConfig(), home=home, root=root, environ={})
    assert loaded.available_models == ("haiku", "sonnet")
    configured = read_agent_launch(
        AgentLaunchConfig(available_models=("opus",)), home=home, root=root, environ={}
    )
    assert configured.available_models == ("opus",)


def test_guvenilmeyen_proje_yonetilen_kok_etiketiyle_kanca_yurutme_acamaz(
    tmp_path, monkeypatch, caplog
):
    from fusion_cli.engines.agent import team_settings
    from fusion_cli.engines.agent.team import resolve_persona
    from fusion_cli.tools.capability_overrides import registry_from_config

    root, home = tmp_path / "project", tmp_path / "home"
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text(
        "---\nname: denetci\ndescription: inceler\nhooks:\n  PreToolUse:\n"
        "    - hooks:\n        - type: command\n          command: SECRET_SENTINEL\n---\nGövde."
    )
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump({"agent_launch": {"managed_agent_roots": [str(agents)]}}))
    monkeypatch.chdir(root)
    monkeypatch.setattr(loader, "load_environment", lambda: None)
    monkeypatch.setattr(loader, "user_config_candidates", lambda: (path,))
    with caplog.at_level(logging.WARNING):
        config = loader.load_config()
    assert config.agent_launch.managed_agent_roots == ()
    persona = resolve_persona(registry_from_config(config, home, root), "denetci")
    assert persona.source == "proje"
    assert not team_settings.is_trusted_agent_definition(config, persona, root=root, home=home)
    assert any("agent_launch" in record.message for record in caplog.records)
