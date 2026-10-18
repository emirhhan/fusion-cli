"""Modeller sekmesi: rol atama ve Codex sağlayıcısı."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.appserver import model_roles
from fusion_cli.config.loader import load_config
from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.providers import codex_cli

YAML = """\
agent:
  name: secilen
  model: gemini_web/main/auto
judge:
  name: secilen
  model: gemini_web/main/auto
candidates:
- name: secilen
  model: gemini_web/main/auto
task_model_map:
  general: secilen
  code: secilen
  reasoning: secilen
  agent: secilen
"""


@pytest.fixture
def config(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(YAML, encoding="utf-8")
    return load_config(path)


def test_ogretmen_atanir_ve_kalici_yazilir(config) -> None:
    yeni = model_roles.apply_role(config, "teacher", "codex_cli/default")
    assert yeni.teacher is not None and yeni.teacher.model == "codex_cli/default"
    assert load_config(config.source).teacher.model == "codex_cli/default"


def test_ogretmen_bos_atanirsa_otomatige_doner(config) -> None:
    model_roles.apply_role(config, "teacher", "codex_cli/default")
    yeni = model_roles.apply_role(config, "teacher", "")
    assert yeni.teacher is None
    assert "teacher" not in config.source.read_text(encoding="utf-8")


def test_adaylar_haritayi_gecerli_tutar(config) -> None:
    secim = ["codex_cli/default", "gemini_web/main/auto"]
    yeni = model_roles.apply_role(config, "candidates", secim)
    assert [c.model for c in load_config(config.source).candidates] == [
        "codex_cli/default",
        "gemini_web/main/auto",
    ]
    assert set(yeni.task_model_map.values()) == {"aday-1"}


def test_bos_aday_listesi_reddedilir(config) -> None:
    ok, sonuc = asyncio.run(model_roles.assign(config, "candidates", []))
    assert ok is None and sonuc["ok"] is False


def test_gecersiz_model_kimligi_reddedilir(config) -> None:
    ok, sonuc = asyncio.run(model_roles.assign(config, "agent", "kimliksiz"))
    assert ok is None and not sonuc["ok"]


def test_codex_kurulu_degilse_hata_doner(monkeypatch) -> None:
    monkeypatch.setattr(codex_cli, "codex_binary", lambda: None)
    sonuc = asyncio.run(
        codex_cli.CodexCliProvider("codex_cli/default").complete(
            CompletionRequest((Message("user", "x"),), 0.0, 10, 5)
        )
    )
    assert not sonuc.ok and "codex" in (sonuc.error or "")


def test_codex_ajan_modeli_olamaz(config) -> None:
    ok, sonuc = asyncio.run(model_roles.assign(config, "agent", "codex_cli/default"))
    assert ok is None and "araç" in sonuc["metin"]


def test_codex_yedegi_varsayilan_kapali_ve_acilip_kapanir(config) -> None:
    from fusion_cli.engines.agent.engine_tools import teacher_candidates

    assert config.runtime.teacher_codex_fallback is False
    acik = model_roles.apply_role(config, "codex_yedek", True)
    assert load_config(config.source).runtime.teacher_codex_fallback is True
    assert acik.runtime.teacher_codex_fallback is True
    kapali = teacher_candidates(config, config.agent)
    assert all(not a.model.startswith("codex_cli/") for a in kapali)


def test_chatgpt_yeni_mesaj_kaplari_once_denenir() -> None:
    """18 Ekim 2026: ChatGPT mesaj işaretini değiştirdi; yeni kaplar ilk sırada olmalı."""
    from fusion_cli.providers.web_browser import provider_definition

    tanim = provider_definition("chatgpt_web")
    assert tanim.response_selectors[0] == '[data-markdown-text-style="assistant-message"]'
    assert '[data-content-search-unit-key$=":assistant"]' in tanim.response_selectors
    assert "[data-content-search-unit-key]" in tanim.history_selectors


def test_ek_gecerli_arguman_korunumu_bozmaz_ama_degisen_deger_bozar() -> None:
    from fusion_cli.tools.emulation_eval import EvalCase, score_emulation

    def cagri(args: str) -> str:
        return (
            'FUSION_TOOL_CALL\n```json\n{"name":"search_code","arguments":' + args + "}\n```\n"
            "FUSION_TOOL_CALL_END"
        )

    beklenen = {"pattern": "TODO"}
    ek = EvalCase(
        output=cagri('{"path":".","pattern":"TODO"}'),
        expected_tool="search_code",
        expected_arguments=beklenen,
    )
    yanlis = EvalCase(
        output=cagri('{"pattern":"FIXME"}'),
        expected_tool="search_code",
        expected_arguments=beklenen,
    )
    assert score_emulation([ek]).argument_preservation == 1.0
    assert score_emulation([yanlis]).argument_preservation == 0.0


def test_yerel_modeller_canlilik_yoklamasina_girmez() -> None:
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.engines.agent.liveness import is_api_model

    assert not is_api_model(ModelSpec(name="a", model="ollama_chat/huihui_ai/qwen3.5:9b"))
    assert not is_api_model(ModelSpec(name="a", model="gemini_web/main/auto"))
    assert is_api_model(ModelSpec(name="a", model="nvidia_nim/nvidia/nemotron-3-ultra"))
