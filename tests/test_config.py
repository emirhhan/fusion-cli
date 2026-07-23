"""Yapılandırma — birleştirme, doğrulama ve varsayılan tutarlılığı."""

from __future__ import annotations

import dataclasses

import pytest
import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.config.models import RuntimeConfig
from fusion_cli.config.paths import bundled_defaults
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.types import ModelSpec


def _yaz(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_kullanici_dosyasi_yoksa_varsayilanlar_yuklenir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FUSION_CONFIG", raising=False)
    monkeypatch.delenv("FUSION_HOME", raising=False)

    config = load_config()

    assert config.source is None
    assert config.agent.model.startswith(("nvidia_nim/", "openrouter/"))


def test_kullanici_dosyasi_varsayilanin_uzerine_derin_birlestirilir(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"max_tokens": 99}})

    config = load_config(path)

    assert config.runtime.max_tokens == 99
    # Dokunulmayan alanlar varsayılandan gelir — bölüm tamamen değiştirilmez.
    assert config.runtime.temperature == 0.3
    assert config.source == path


def test_bilinmeyen_bolum_hata_verir(tmp_path):
    path = _yaz(tmp_path, {"bilinmeyen_bolum": {}})

    with pytest.raises(ConfigError, match="bilinmeyen anahtar"):
        load_config(path)


def test_bilinmeyen_alan_hata_verir(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"yanlis_alan": 1}})

    with pytest.raises(ConfigError, match="yanlis_alan"):
        load_config(path)


def test_yanlis_tip_hata_verir(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"max_tokens": "cok"}})

    with pytest.raises(ConfigError, match="tam sayı bekleniyordu"):
        load_config(path)


def test_boolean_tam_sayi_yerine_gecemez(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"max_tokens": True}})

    with pytest.raises(ConfigError, match="boolean"):
        load_config(path)


def test_liste_beklenen_yere_sayi_verilemez(tmp_path):
    """Tek METİN kabul edilir (bkz. eski biçim uyumu) ama sayı kabul edilmez."""
    path = _yaz(tmp_path, {"agent": {"fallback": 3}})

    with pytest.raises(ConfigError, match="liste bekleniyordu"):
        load_config(path)


def test_olmayan_dosya_anlasilir_hata_verir(tmp_path):
    with pytest.raises(ConfigError, match="bulunamadı"):
        load_config(tmp_path / "yok.yaml")


def test_bozuk_yaml_anlasilir_hata_verir(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("agent: [bozuk", encoding="utf-8")

    with pytest.raises(ConfigError, match="geçerli YAML değil"):
        load_config(path)


def test_varsayilanlar_dosyasi_tum_zorunlu_alanlari_icerir():
    """Kod ile dosya arasındaki varsayılan sapmasını imkânsız kılan koruma.

    Eski projede aynı varsayılan hem kodda hem YAML'da duruyordu ve zamanla ayrıştı.
    Artık varsayılanın tek kaynağı `defaults.yaml`; bir alan unutulursa bu test kırılır.
    """
    defaults = yaml.safe_load(bundled_defaults().read_text(encoding="utf-8"))

    for section, cls in (("agent", ModelSpec), ("runtime", RuntimeConfig)):
        zorunlu = {
            field.name
            for field in dataclasses.fields(cls)
            if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
        }
        assert zorunlu <= set(defaults[section]), f"{section} bölümünde eksik alan var"


def test_models_birincil_ve_yedekleri_sirayla_tekilleştirir():
    spec = ModelSpec(name="a", model="m1", fallback=("m2", "m1", "m3"))

    assert spec.models == ("m1", "m2", "m3")


# --- Eski biçimle uyum --------------------------------------------------------- #


def test_tek_metin_yedek_liste_sayilir(tmp_path):
    """Önceki sürüm `fallback: str | list[str]` kabul ediyordu; kırılmamalı."""
    yol = tmp_path / "config.yaml"
    yol.write_text(
        "candidates:\n"
        "  - name: tek\n"
        "    model: saglayici/model\n"
        "    tags: [general]\n"
        "    fallback: saglayici/yedek\n"
        "task_model_map:\n"
        "  general: tek\n"
        "  code: tek\n"
        "  reasoning: tek\n"
        "  agent: tek\n",
        encoding="utf-8",
    )

    config = load_config(yol)

    assert config.candidates[0].fallback == ("saglayici/yedek",)


def test_tek_metin_etiket_de_liste_sayilir(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("agent:\n  fallback: saglayici/yedek\n", encoding="utf-8")

    assert load_config(yol).agent.fallback == ("saglayici/yedek",)


def test_hata_mesaji_suclu_dosyayi_soyler(tmp_path):
    """Config birden çok yerde aranıyor; hangisinin bozuk olduğu yazmalı."""
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  max_tokens: cok\n", encoding="utf-8")

    with pytest.raises(ConfigError) as hata:
        load_config(yol)

    assert str(yol) in str(hata.value)


def test_adi_degisen_ayar_eski_adiyla_da_calisir(tmp_path):
    """`agent_max_iterations` → `agent_max_steps`; yeniden adlandırma kullanıcıyı vurmamalı."""
    path = _yaz(tmp_path, {"runtime": {"agent_max_iterations": 42}})

    assert load_config(path).runtime.agent_max_steps == 42


def test_yeni_ad_yazilmissa_eski_ad_onu_ezmez(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"agent_max_iterations": 42, "agent_max_steps": 7}})

    assert load_config(path).runtime.agent_max_steps == 7


def test_tasinmamis_ayar_sebebiyle_reddedilir(tmp_path):
    """Genel 'bilinmeyen anahtar' listesi yerine ne olduğunu söylemeli."""
    path = _yaz(tmp_path, {"runtime": {"live_input": True}})

    with pytest.raises(ConfigError, match="artık yok"):
        load_config(path)
