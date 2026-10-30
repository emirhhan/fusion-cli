"""Godot yürütülebilir keşfi: GODOT_BIN, sonra PATH, sonra uygulama paketi (E1-10).

Ölçüldü (30 Ekim): kapı komutu hep literal `godot`; macOS'ta Godot çoğu kurulumda
PATH'te değildir (`/Applications/Godot.app/Contents/MacOS/Godot`), kapı "command not
found" (127) ile doğrulanamıyordu.
"""

from __future__ import annotations

import os

from fusion_cli.engines.agent.domain_adapters.godot import (
    find_godot_executable,
    godot_adapter,
)

_ANA_SAHNELI = 'config_version=5\n[application]\nrun/main_scene="res://ana.tscn"\n'


def _calistirilabilir(yol):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("#!/bin/sh\n", encoding="utf-8")
    yol.chmod(0o755)
    return yol


def test_godot_bin_ortam_degiskeni_once_gelir(tmp_path):
    ozel = _calistirilabilir(tmp_path / "ozel" / "godot4")

    bulunan = find_godot_executable(
        {"GODOT_BIN": str(ozel)}, which=lambda ad: "/usr/bin/godot", bundles=()
    )

    assert bulunan == str(ozel)


def test_gecersiz_godot_bin_atlanir_ve_path_denenir(tmp_path):
    bulunan = find_godot_executable(
        {"GODOT_BIN": str(tmp_path / "yok")}, which=lambda ad: "/usr/bin/godot", bundles=()
    )

    assert bulunan == "/usr/bin/godot"


def test_path_yoksa_uygulama_paketine_dusulur(tmp_path):
    paket = _calistirilabilir(tmp_path / "Godot.app" / "Contents" / "MacOS" / "Godot")

    bulunan = find_godot_executable({}, which=lambda ad: None, bundles=(paket,))

    assert bulunan == str(paket)


def test_hicbiri_yoksa_none(tmp_path):
    assert find_godot_executable({}, which=lambda ad: None, bundles=(tmp_path / "yok",)) is None


def test_kapi_komutu_bulunan_yolu_alintilayarak_kullanir(tmp_path, monkeypatch):
    paket = _calistirilabilir(tmp_path / "Godot Engine.app" / "Contents" / "MacOS" / "Godot")
    monkeypatch.setenv("GODOT_BIN", str(paket))
    (tmp_path / "proje").mkdir()
    proje = tmp_path / "proje"
    (proje / "project.godot").write_text(_ANA_SAHNELI, encoding="utf-8")
    (proje / "ana.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")

    (komut,) = godot_adapter().gate_commands(proje)

    assert komut == f"'{paket}' --headless --path . --quit"


def test_godot_path_teyse_komut_degismez(tmp_path, monkeypatch):
    monkeypatch.delenv("GODOT_BIN", raising=False)
    monkeypatch.setattr(
        "fusion_cli.engines.agent.domain_adapters.godot.shutil.which",
        lambda ad, *a, **k: "/usr/local/bin/godot",
    )
    (tmp_path / "project.godot").write_text(_ANA_SAHNELI, encoding="utf-8")
    (tmp_path / "ana.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")

    assert godot_adapter().gate_commands(tmp_path) == ("godot --headless --path . --quit",)
    assert os.environ.get("GODOT_BIN") is None
