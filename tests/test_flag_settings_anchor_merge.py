"""Birleştirme kapısı: `--settings` okuyucuları dayanağı kaydeder (#45).

`config.flag_settings_anchor.record_settings_flag` bu dalda testli, ama bayrağı okuyan iki
taraf (`cli/print_settings.root_settings`, `cli/print_plan._build_config`) headless-cli
dalında. O modüller yokken testler atlanır; birleştirmeden sonra çağrı eklenmemişse KIRMIZI
olur: `--settings izinler.json` içindeki `Read(/secrets/**)` deny kuralı dosyanın dizinine
değil proje köküne bağlanır (fail-open). Uçtan uca: bayrak → kayıt → izin kararı.

Birleştirmede eklenecek iki satır (1 Kasım'da headless-cli kodu üzerinde denendi: kırmızı →
yeşil): `root_settings` içinde `load_settings(raw)` yanına `record_settings_flag(raw)`;
`_build_config` içinde `opts.load_settings(request.settings)` yanına
`record_settings_flag(request.settings)` (`from ..config.flag_settings_anchor import ...`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config.flag_settings_anchor import FLAG_SETTINGS_DIR_ENV, flag_settings_dir
from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.tools.permission_match import evaluate

from .fakes import make_config


@pytest.fixture(autouse=True)
def _temiz_ortam(monkeypatch, tmp_path):
    monkeypatch.setenv(FLAG_SETTINGS_DIR_ENV, "")
    monkeypatch.delenv(FLAG_SETTINGS_DIR_ENV)
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))


def _ayar_dosyasi(tmp_path: Path) -> Path:
    dosya = tmp_path / "ayarlar" / "izinler.json"
    dosya.parent.mkdir()
    dosya.write_text(json.dumps({"permissions": {"deny": ["Read(/secrets/**)"]}}), encoding="utf-8")
    return dosya


def _dosya_dizinine_bagli(dosya: Path, kok: Path, kaynak: str) -> None:
    assert flag_settings_dir() == dosya.parent.resolve()
    kural = parse_rule("Read(/secrets/**)", PermissionDecision.DENY, source=kaynak)
    assert kural is not None
    kume = PermissionRuleSet(rules=(kural,))
    hedef = str(dosya.parent / "secrets" / "a")
    sonuc = evaluate(kume, "read_file", {"path": hedef}, kok)
    assert sonuc is not None and sonuc.decision is PermissionDecision.DENY


def test_kok_komut_settings_dosyasinin_dizinini_kaydeder(tmp_path):
    print_settings = pytest.importorskip("fusion_cli.cli.print_settings")
    kok = tmp_path / "proje"
    kok.mkdir()
    dosya = _ayar_dosyasi(tmp_path)
    print_settings.root_settings(make_config(), str(dosya), None)
    _dosya_dizinine_bagli(dosya, kok, "bayrak")


def test_print_kipi_settings_dosyasinin_dizinini_kaydeder(tmp_path, monkeypatch):
    print_plan = pytest.importorskip("fusion_cli.cli.print_plan")
    kok = tmp_path / "proje"
    kok.mkdir()
    dosya = _ayar_dosyasi(tmp_path)
    monkeypatch.setattr(print_plan, "load_config", make_config)
    print_plan._build_config(print_plan.PrintRequest(settings=str(dosya)))
    _dosya_dizinine_bagli(dosya, kok, "--settings")
