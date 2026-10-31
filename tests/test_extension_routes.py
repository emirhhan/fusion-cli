"""Masaüstü RPC'leri (P-059, P-071): `eklenti.*`, `ice_aktar.*`, `surum.notlari`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fusion_cli.appserver.extension_routes import ExtensionContext, dispatch_extension
from fusion_cli.config.loader import load_config


def _context(tmp_path: Path) -> ExtensionContext:
    home, root = tmp_path / "ev", tmp_path / "proje"
    home.mkdir()
    root.mkdir()
    config_file = tmp_path / "config.yaml"
    config_file.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ExtensionContext(root, home, load_config(config_file))


def _call(name: str, data: dict[str, object], context: ExtensionContext) -> dict[str, object]:
    return asyncio.run(dispatch_extension(name, data, context)).payload


def _hooked_plugin(folder: Path) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "bicimci", "version": "0.1.0"}), encoding="utf-8"
    )
    (folder / "hooks").mkdir()
    (folder / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]}}),
        encoding="utf-8",
    )
    return folder


def test_kanca_iceren_eklenti_onaysiz_onay_gerekli_doner_onayla_kurulur(tmp_path):
    context = _context(tmp_path)
    source = str(_hooked_plugin(tmp_path / "kaynak"))

    first = _call("eklenti.kur", {"kaynak": source}, context)
    assert first["ok"] is False and first["onay_gerekli"] is True
    assert first["onizleme"]["kanca_sayisi"] == 1  # type: ignore[index]

    second = _call("eklenti.kur", {"kaynak": source, "onay": True}, context)
    assert second["ok"] is True and second["yenile"] is True
    listed = _call("eklenti.listele", {}, context)
    (row,) = listed["eklentiler"]  # type: ignore[misc]
    assert row["ad"] == "bicimci" and row["calistirilabilir"] is True

    off = _call("eklenti.etkinlik", {"ad": "bicimci", "etkin": False}, context)
    assert off["eklentiler"][0]["durum"] == "kapalı"  # type: ignore[index]
    removed = _call("eklenti.kaldir", {"ad": "bicimci"}, context)
    assert removed["eklentiler"] == []


def test_ice_aktar_onizle_ve_uygula(tmp_path):
    context = _context(tmp_path)
    prompts = context.home / ".codex" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "x.md").write_text("X\n", encoding="utf-8")

    preview = _call("ice_aktar.onizle", {"kaynak": "codex"}, context)
    assert preview["eklenecek"] == 1
    applied = _call("ice_aktar.uygula", {"kaynak": "codex"}, context)
    assert applied["ok"] is True and applied["uygulanan"] == 1
    assert (context.home / ".fusion" / "commands" / "x.md").is_file()
    assert _call("ice_aktar.onizle", {"kaynak": "yok"}, context)["ok"] is False


def test_surum_notlari_ve_bilinmeyen_istek(tmp_path):
    context = _context(tmp_path)
    notes = _call("surum.notlari", {}, context)
    assert notes["ok"] is True and notes["kurulu"]
    assert notes["bolumler"]
    assert _call("eklenti.yok", {}, context)["ok"] is False
    assert _call("eklenti.kur", {}, context)["ok"] is False
