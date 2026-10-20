"""Tema tercihi KALICI olmalı ve yazma hatası sessizce yutulmamalı.

Ölçüldü (11 Eylül, kullanıcı makinesi): macOS koyu temadayken Fusion içeriği
beyaz kalıyordu. Sebep zincirinin ucu şuydu — tercih webview `localStorage`'ında
tutuluyor ve o depo bu kurulumda hiç yazılmıyor:

    ~/Library/WebKit/com.fusion.desktop/WebsiteData/LocalStorage → 0 bayt

Yazma hatası `try/except` ile yutulduğu için tercih her açılışta `system`'e
düşüyor, kullanıcı Ayarlar'dan koyuyu seçse bile bir sonraki açılışta unutuluyordu.
Kalıcılık, zaten sınanmış olan yapılandırma katmanına taşınır.
"""

from __future__ import annotations

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.config.writer import write_theme

from .fakes import make_config


def test_tema_yazilip_geri_okunur(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)

    write_theme(config, "dark", hedef)

    assert load_config(hedef).runtime.theme == "dark"


def test_tema_yazarken_runtime_ayarlari_korunur(tmp_path):
    """Kullanıcının bütçe ayarları tema değişince sıfırlanmamalı."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  workflow_step_calls: 40\n  provider: nvidia\n", encoding="utf-8")
    config = make_config(source=hedef)

    write_theme(config, "light", hedef)

    geri = load_config(hedef)
    assert geri.runtime.theme == "light"
    assert geri.runtime.workflow_step_calls == 40


def test_gecersiz_tema_reddedilir(tmp_path):
    """Tanınmayan değer sessizce kabul edilirse arayüz çözemeyeceği durum görür."""
    with pytest.raises(ValueError, match="tema"):
        write_theme(make_config(source=tmp_path / "c.yaml"), "mor", tmp_path / "c.yaml")


def test_varsayilan_sistem_temasidir():
    assert make_config().runtime.theme == "system"
