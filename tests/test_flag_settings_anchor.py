"""`--settings` dosyasındaki `/x` kalıbı o dosyanın dizinine bağlanır (#45).

Kaynak: code.claude.com/docs/en/permissions#where-a-pattern-anchors — `/path` ayar
kaynağına göre çözülür: kullanıcı ayarında `~/.claude/path`, `--settings` dosyasında o
dosyanın dizini; satır içi JSON ile verilen `--settings` ve öteki kaynaklarda proje kökü.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config.flag_settings_anchor import (
    FLAG_LAYER_NAME,
    FLAG_SETTINGS_DIR_ENV,
    flag_settings_dir,
    set_flag_settings_dir,
)
from fusion_cli.config.permission_rules import (
    PermissionDecision,
    PermissionRuleSet,
    parse_rule,
)
from fusion_cli.tools.permission_match import evaluate


@pytest.fixture(autouse=True)
def _temiz_ortam(monkeypatch):
    # setenv önceki durumu kaydeder: test içinde süreç ortamına yazılan değer geri alınır.
    monkeypatch.setenv(FLAG_SETTINGS_DIR_ENV, "")
    monkeypatch.delenv(FLAG_SETTINGS_DIR_ENV)


def _kume(metin: str, source: str) -> PermissionRuleSet:
    kural = parse_rule(metin, PermissionDecision.DENY, source=source)
    assert kural is not None
    return PermissionRuleSet(rules=(kural,))


def _karar(kume: PermissionRuleSet, yol: str, kok: Path):
    sonuc = evaluate(kume, "read_file", {"path": yol}, kok)
    return None if sonuc is None else sonuc.decision


def test_settings_dosyasindaki_egik_cizgi_dosyanin_dizinine_baglanir(tmp_path):
    kok = tmp_path / "proje"
    ayar_dizini = tmp_path / "ayarlar"
    kok.mkdir()
    ayar_dizini.mkdir()
    set_flag_settings_dir(ayar_dizini / "izinler.json")
    assert flag_settings_dir() == ayar_dizini.resolve()
    kume = _kume("Read(/secrets/**)", FLAG_LAYER_NAME)
    assert _karar(kume, str(ayar_dizini / "secrets" / "a"), kok) is PermissionDecision.DENY
    assert _karar(kume, "secrets/a", kok) is None


def test_satir_ici_json_ve_ayar_yoksa_proje_kokune_baglanir(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    set_flag_settings_dir(None)
    kume = _kume("Read(/secrets/**)", FLAG_LAYER_NAME)
    assert _karar(kume, "secrets/a", kok) is PermissionDecision.DENY


def test_baska_kaynak_settings_dizinini_kullanmaz(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    set_flag_settings_dir(tmp_path / "ayarlar" / "izinler.json")
    kume = _kume("Read(/secrets/**)", "proje")
    assert _karar(kume, "secrets/a", kok) is PermissionDecision.DENY
    set_flag_settings_dir(None)
    assert flag_settings_dir() is None
