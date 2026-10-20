"""Model penceresi ile özetleme eşiği birbirine karıştırılmamalı."""

from __future__ import annotations

from fusion_cli.config.loader import load_config
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import context_budget as budget_module
from fusion_cli.providers.context_window import input_window_tokens


def test_bilinen_dar_modelin_esigi_duser(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    config = load_config(config_file)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: 32_000)

    budget = budget_module.context_budget(
        config, ModelSpec("secilen", "openrouter/model", tags=("strict",))
    )

    assert budget.window_tokens == 32_000
    assert budget.compression_chars == 29_712


def test_bilinmeyen_modelin_penceresi_uydurulmaz(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    config = load_config(config_file)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: None)

    budget = budget_module.context_budget(config, ModelSpec("secilen", "nvidia_nim/model"))

    assert budget.window_tokens is None
    assert budget.compression_chars == 177_000


def test_kucuk_model_penceresinde_cikti_payi_tum_butceyi_yemez(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    config = load_config(config_file)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: 8_000)

    budget = budget_module.context_budget(config, ModelSpec("kucuk", "openrouter/kucuk"))

    assert budget.compression_chars == 6_000


def test_yedek_penceresi_bilinmiyorsa_kati_sinir_korunur(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    config = load_config(config_file)
    monkeypatch.setattr(
        budget_module,
        "input_window_tokens",
        lambda model: 262_144 if model == "openrouter/birincil" else None,
    )

    budget = budget_module.context_budget(
        config, ModelSpec("zincir", "openrouter/birincil", fallback=("nvidia_nim/yedek",))
    )

    assert budget.window_tokens is None
    assert budget.compression_chars == 177_000


def test_web_zinciri_web_ozetleme_esigini_kullanir(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    config = load_config(config_file)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: 262_144)

    budget = budget_module.context_budget(config, ModelSpec("web", "chatgpt_web/main/auto"))

    assert budget.window_tokens is None
    assert budget.compression_chars == 24_000


def test_model_penceresi_yalniz_pozitif_girdi_token_meta_verisinden_okunur(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    input_window_tokens.cache_clear()
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(get_model_info=lambda model: {"max_input_tokens": 65_536}),
    )
    assert input_window_tokens("openrouter/known") == 65_536
    input_window_tokens.cache_clear()
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(get_model_info=lambda model: {"max_tokens": 200_000}),
    )
    assert input_window_tokens("openrouter/unknown") is None
    input_window_tokens.cache_clear()
