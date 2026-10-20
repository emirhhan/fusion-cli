"""Bir sonraki açılışta gösterilecek TEK SEFERLİK "çırağa dön" bildirimi (Görev 2, §6.1).

İşaret `config.yaml`'a YAZILMAZ (o dosya `config/writer.py`'nin dar sözleşmesidir,
bkz. RULES "Yapılandırma": "aynı içeriğin ikinci bir kopyası tutulmaz" — burada
YENİ bir anahtar eklemek o sözleşmeyi genişletirdi); kullanıcı yapılandırma
dizininin YANINDA ayrı, dar bir durum dosyasında tutulur.
"""

from __future__ import annotations

from fusion_cli.config.apprentice_notice import (
    apprentice_notice_shown,
    mark_apprentice_notice_shown,
)


def test_ilk_acilista_bildirim_gosterilmemis_sayilir(tmp_path):
    assert apprentice_notice_shown(tmp_path) is False


def test_isaretlendikten_sonra_bir_daha_gosterilmez(tmp_path):
    mark_apprentice_notice_shown(tmp_path)

    assert apprentice_notice_shown(tmp_path) is True


def test_isaret_config_yaml_dosyasina_yazilmaz(tmp_path):
    mark_apprentice_notice_shown(tmp_path)

    assert not (tmp_path / "config.yaml").exists()


def test_dizin_yoksa_isaretleme_dizini_olusturur(tmp_path):
    hedef = tmp_path / "henuz-yok"

    mark_apprentice_notice_shown(hedef)

    assert apprentice_notice_shown(hedef) is True
