"""Seçilen modellerin kullanıcı yapılandırmasına kalıcı yazılması."""

from __future__ import annotations

import pytest
import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.config.model_select import apply_tier
from fusion_cli.config.writer import write_model_section
from fusion_cli.core.errors import ConfigError


def test_yazilan_dosya_geri_okununca_ayni_modelleri_verir(tmp_path):
    """Round-trip: yazmak ile yüklemek birbirinin tersi olmalı."""
    hedef = tmp_path / "config.yaml"
    secilen = apply_tier(load_config(), "premium")

    write_model_section(secilen, hedef)
    geri = load_config(hedef)

    assert geri.agent == secilen.agent
    assert geri.judge == secilen.judge
    assert geri.candidates == secilen.candidates


def test_her_kademe_yazilip_geri_okunabilir(tmp_path):
    """Bir kademe yazıldığında yükleyicinin doğrulamasından geçmeli."""
    config = load_config()

    for kademe in config.tiers:
        hedef = tmp_path / f"{kademe.name}.yaml"
        secilen = apply_tier(config, kademe.name)

        write_model_section(secilen, hedef)

        assert load_config(hedef).agent == secilen.agent


def test_gorev_haritasi_da_yazilir(tmp_path):
    """Harita yazılmazsa dosya yüklenemez: harita eski kademenin adlarını işaret eder.

    Aday havuzu değişip harita eski hâlinde kalsaydı yükleyici "adlı aday tanımlı
    değil" hatası verir ve kullanıcı uygulamayı bir daha hiç açamazdı.
    """
    hedef = tmp_path / "config.yaml"
    secilen = apply_tier(load_config(), "premium")

    write_model_section(secilen, hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    adaylar = {aday["name"] for aday in yazilan["candidates"]}
    assert set(yazilan["task_model_map"].values()) <= adaylar


def test_diger_bolumlere_dokunulmaz(tmp_path):
    """Kullanıcının elle ayarladığı bölümler yeniden yazımda kaybolmamalı."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text(
        yaml.safe_dump({"runtime": {"max_tokens": 99}, "embedding": {"provider": "nim"}}),
        encoding="utf-8",
    )

    write_model_section(apply_tier(load_config(), "high"), hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    assert yazilan["runtime"]["max_tokens"] == 99
    assert yazilan["embedding"]["provider"] == "nim"


def test_kademe_tanimlari_yazilmaz(tmp_path):
    """`tiers` varsayılanların işidir; kopyalanırsa ikinci bir kaynak oluşurdu."""
    hedef = tmp_path / "config.yaml"

    write_model_section(apply_tier(load_config(), "ultra"), hedef)

    assert "tiers" not in yaml.safe_load(hedef.read_text(encoding="utf-8"))


def test_dosya_yoksa_olusturulur(tmp_path):
    hedef = tmp_path / "yeni" / "config.yaml"

    yazilan = write_model_section(load_config(), hedef)

    assert yazilan == hedef
    assert hedef.is_file()


def test_bos_alanlar_yazilmaz(tmp_path):
    """`tags: []` ve `fallback: []` satırları gürültüden başka bir şey değil."""
    hedef = tmp_path / "config.yaml"

    write_model_section(apply_tier(load_config(), "low"), hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    assert all(deger for aday in yazilan["candidates"] for deger in aday.values())


def test_bozuk_yaml_uzerine_yazilmaz(tmp_path):
    """Sessizce ezmek kullanıcının ayarlarını kaybettirirdi."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text("agent: [kapanmamis\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="geçerli YAML değil"):
        write_model_section(load_config(), hedef)


def test_yazim_atomiktir_gecici_dosya_birakilmaz(tmp_path):
    hedef = tmp_path / "config.yaml"

    write_model_section(load_config(), hedef)

    assert [item.name for item in tmp_path.iterdir()] == ["config.yaml"]
