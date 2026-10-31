"""Masaüstü RPC'leri (P-071): `ice_aktar.*`, `surum.notlari`."""

from __future__ import annotations

import asyncio
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
