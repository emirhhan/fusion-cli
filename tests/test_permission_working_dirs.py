"""Çalışma dizinleri ve kök dışı okuma ayarı Claude Code ile birebir (#57, #76).

Kaynak: https://code.claude.com/docs/en/permissions#working-directories ;
https://code.claude.com/docs/en/settings-reference (blockReadsOutsideWorkingDirectories).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.config import trust
from fusion_cli.config.loader import _with_claude_read_block
from fusion_cli.config.permission_settings import working_directories


@pytest.fixture
def proje(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


def _yaz(yol: Path, veri: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri), encoding="utf-8")


def test_kullanici_additional_directories_ek_dizin_olur(proje, tmp_path):
    ek = tmp_path / "paylasilan"
    ek.mkdir()
    _yaz(
        Path.home() / ".claude" / "settings.json",
        {"permissions": {"additionalDirectories": [str(ek), str(tmp_path / "yok")]}},
    )
    bayrak = tmp_path / "bayrak"
    assert working_directories(proje, (bayrak,)) == (bayrak, ek.resolve())


def test_guvenilmeyen_proje_additional_directories_okunmaz(proje, tmp_path):
    ek = tmp_path / "disari"
    ek.mkdir()
    _yaz(proje / ".claude" / "settings.json", {"permissions": {"additionalDirectories": [str(ek)]}})
    assert working_directories(proje) == ()


def test_repl_durumu_ayardaki_dizinleri_alir(proje, tmp_path):
    from fusion_cli.cli.repl.state import _apply_additional_directories

    ek = tmp_path / "ortak"
    ek.mkdir()
    _yaz(
        Path.home() / ".claude" / "settings.json",
        {"permissions": {"additionalDirectories": [str(ek)]}},
    )
    durum = SimpleNamespace(root=proje, extra_roots=())
    _apply_additional_directories(durum)
    assert durum.extra_roots == (ek.resolve(),)


@dataclasses.dataclass(frozen=True)
class _Runtime:
    block_reads_outside_root: bool = False


@dataclasses.dataclass(frozen=True)
class _Config:
    runtime: _Runtime = _Runtime()


def test_block_reads_her_kapsamdan_true_olarak_gecer(proje):
    assert _with_claude_read_block(_Config(), proje).runtime.block_reads_outside_root is False
    # Güvenilmeyen proje dosyasındaki `true` de geçerlidir (kısıtlayıcıdır).
    _yaz(
        proje / ".claude" / "settings.json",
        {"permissions": {"blockReadsOutsideWorkingDirectories": True}},
    )
    assert _with_claude_read_block(_Config(), proje).runtime.block_reads_outside_root is True
