"""Sağlayıcı anahtarlarına göre model zincirlerinin budanması."""

from __future__ import annotations

import pytest

from fusion_cli.config.keys import ProviderKeys, detect, prune_config
from fusion_cli.config.loader import load_config


def test_dolu_anahtar_kurulu_sayilir():
    keys = detect({"OPENROUTER_API_KEY": "sk-x", "NVIDIA_NIM_API_KEY": "nv-y"})

    assert keys.openrouter and keys.nim and keys.any_configured


def test_bos_anahtar_kurulu_sayilmaz():
    """`.env` şablonu anahtarları boş bırakır; boş satır kurulum sayılmamalı."""
    keys = detect({"OPENROUTER_API_KEY": "", "NVIDIA_NIM_API_KEY": "   "})

    assert not keys.openrouter and not keys.nim and not keys.any_configured


def test_taninmayan_saglayici_engellenmez():
    """Yerel/özel uçların anahtar gereksinimini bilemeyiz; kullanıcı bilerek yazmıştır."""
    keys = ProviderKeys(openrouter=False, nim=False)

    assert keys.supports("ollama/qwen2.5-coder:7b") is True
    assert keys.supports("openrouter/x:free") is False
    assert keys.supports("nvidia_nim/y") is False


def test_nim_yokken_nim_modelleri_zincirden_dusurulur():
    config = load_config()
    keys = ProviderKeys(openrouter=True, nim=False)

    budanmis = prune_config(config, keys)

    for kademe in budanmis.tiers:
        for spec in (kademe.agent, kademe.judge, *kademe.candidates):
            assert all(not m.startswith("nvidia_nim/") for m in spec.models), spec.models


def test_budama_her_role_calisir_model_birakir():
    """Budama bir rolü boşaltmamalı: modelsiz rol turu çökertir."""
    config = load_config()

    for keys in (ProviderKeys(True, False), ProviderKeys(True, True)):
        budanmis = prune_config(config, keys)
        for kademe in budanmis.tiers:
            for spec in (kademe.agent, kademe.judge, *kademe.candidates):
                assert spec.models, f"{kademe.name} rolü boş kaldı"
        assert budanmis.agent.models and budanmis.judge.models


def test_yalnizca_nim_varsa_openrouter_dusurulur_ama_rol_bosalmaz():
    """NIM tek başına da yeterli olmalı."""
    config = load_config()
    keys = ProviderKeys(openrouter=False, nim=True)

    budanmis = prune_config(config, keys)

    for spec in (budanmis.agent, budanmis.judge, *budanmis.candidates):
        assert spec.models, "yalnızca NIM varken de her rol çalışabilmeli"


def test_hicbir_anahtar_yoksa_yapilandirma_degismez():
    """Budama kurulum eksikliğini gizlememeli; hata mesajı bunu söyleyecek."""
    config = load_config()

    assert prune_config(config, ProviderKeys(False, False)) is config


@pytest.mark.parametrize("keys", [ProviderKeys(True, True)])
def test_iki_anahtar_da_varsa_hicbir_sey_budanmaz(keys):
    config = load_config()

    assert prune_config(config, keys) is config


# --- Sağlayıcı tercihi ------------------------------------------------------- #


def test_nvidia_tercihinde_openrouter_zincirden_cikar():
    """Bir sağlayıcının tükenmesi ötekini de tüketmemeli.

    Gerçek olay: NIM kredisi bitince her çağrı yedeğe düştü, hepsi OpenRouter'a
    gitti ve günlük 50 istek birkaç dakikada tükendi. Kullanıcı tek sağlayıcıya
    kilitlenebilmeli; o zaman ötekinin kotası HİÇ harcanmaz.
    """
    from fusion_cli.config.keys import ProviderPreference, apply_preference

    config = load_config()

    secilmis = apply_preference(config, ProviderPreference.NVIDIA)

    for kademe in secilmis.tiers:
        for spec in (kademe.agent, kademe.judge, *kademe.candidates):
            assert all(not m.startswith("openrouter/") for m in spec.models), spec.models


def test_openrouter_tercihinde_nim_zincirden_cikar():
    from fusion_cli.config.keys import ProviderPreference, apply_preference

    secilmis = apply_preference(load_config(), ProviderPreference.OPENROUTER)

    for spec in (secilmis.agent, secilmis.judge, *secilmis.candidates):
        assert all(not m.startswith("nvidia_nim/") for m in spec.models), spec.models


def test_otomatik_tercihte_zincir_degismez():
    """Varsayılan davranış korunur: iki sağlayıcı da zincirde kalır."""
    from fusion_cli.config.keys import ProviderPreference, apply_preference

    config = load_config()

    assert apply_preference(config, ProviderPreference.AUTO) is config


def test_tercih_hicbir_rolu_bosaltmaz():
    """Modelsiz rol turu çökertir; tercih bir rolü boşaltacaksa uygulanmaz."""
    from fusion_cli.config.keys import ProviderPreference, apply_preference

    for tercih in (ProviderPreference.NVIDIA, ProviderPreference.OPENROUTER):
        secilmis = apply_preference(load_config(), tercih)
        for kademe in secilmis.tiers:
            for spec in (kademe.agent, kademe.judge, *kademe.candidates):
                assert spec.models, f"{kademe.name} rolü {tercih} ile boş kaldı"


def test_taninmayan_saglayici_tercihten_etkilenmez():
    """Yerel/özel uçlar (ollama, vLLM) yönettiğimiz iki sağlayıcıdan biri değildir."""
    from dataclasses import replace

    from fusion_cli.config.keys import ProviderPreference, apply_preference
    from fusion_cli.core.types import ModelSpec

    config = load_config()
    yerel = ModelSpec(name="yerel", model="ollama/qwen2.5-coder:7b")
    ozel = replace(config, agent=yerel)

    secilmis = apply_preference(ozel, ProviderPreference.NVIDIA)

    assert secilmis.agent.models == ("ollama/qwen2.5-coder:7b",)
