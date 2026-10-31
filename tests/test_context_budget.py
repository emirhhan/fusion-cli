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
    # 32.000 - min(8.192 + 10.000, 16.000) = 16.000 kullanılabilir; yarısı × 3 karakter
    # = 24.000 (genel formül; sistem+araç payı: A1-04, 29 Ekim). 32.000 <= 32.768 olduğu
    # için model ZAYIFTIR: eşik pencerenin %20'sine (32.000 × 0,2 × 3 = 19.200) iner.
    assert budget.compression_chars == 19_200
    assert budget.weak is True


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

    # Genel formül 6.000; 8.000 token zayıf sayılır: 8.000 × 0,2 × 3 = 4.800.
    assert budget.compression_chars == 4_800


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


def _config(tmp_path, yaml_text: str = "{}\n"):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml_text, encoding="utf-8")
    return load_config(config_file)


def test_zayif_model_orani_kapatilirsa_genel_formul_gecerli(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path, "runtime:\n  weak_model_compaction_ratio: 0\n")
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: 32_000)

    budget = budget_module.context_budget(config, ModelSpec("s", "openrouter/m", tags=("strict",)))

    assert budget.compression_chars == 24_000 and budget.weak is False


def test_compact_etiketli_genis_pencereli_model_erken_siktirilir(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: 262_144)

    normal = budget_module.context_budget(config, ModelSpec("s", "openrouter/m", tags=("strict",)))
    zayif = budget_module.context_budget(
        config, ModelSpec("s", "openrouter/m", tags=("strict", "compact"))
    )

    # Genel formül geniş pencerede 177.000'e yakın bir eşik verir; zayıf model
    # pencerenin %20'sinde (262.144 × 0,2 × 3 = 157.286) sıkıştırılır.
    assert normal.weak is False and zayif.weak is True
    assert zayif.compression_chars == 157_286 < normal.compression_chars


def test_penceresi_bilinmeyen_compact_model_basvuru_penceresinden_hesaplanir(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: None)

    budget = budget_module.context_budget(config, ModelSpec("s", "nvidia_nim/m", tags=("compact",)))

    # 131.072 × 0,2 × 3 = 78.643 (177.000'den düşük).
    assert budget.window_tokens is None and budget.compression_chars == 78_643


def test_guclu_model_esigi_degismez(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(budget_module, "input_window_tokens", lambda model: 1_000_000)

    budget = budget_module.context_budget(config, ModelSpec("s", "openrouter/m", tags=("strict",)))

    assert budget.weak is False
    reserved = budget_module.OUTPUT_RESERVE_TOKENS + budget_module.SYSTEM_AND_TOOLS_RESERVE_TOKENS
    assert budget.compression_chars == round((1_000_000 - reserved) * 0.5 * 3)


def test_zayif_model_orani_aralik_disiysa_yukleme_reddeder(tmp_path) -> None:
    import pytest

    from fusion_cli.core.errors import ConfigError

    with pytest.raises(ConfigError, match="weak_model_compaction_ratio"):
        _config(tmp_path, "runtime:\n  weak_model_compaction_ratio: 1.5\n")
    with pytest.raises(ConfigError, match="tool_output_window"):
        _config(tmp_path, "runtime:\n  tool_output_window: -1\n")


def test_varsayilanlar_gerekceli_degerlerdir(tmp_path) -> None:
    config = _config(tmp_path)

    assert config.runtime.tool_output_window == 8
    assert config.runtime.weak_model_compaction_ratio == 0.2
