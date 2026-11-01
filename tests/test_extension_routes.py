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


def test_guven_onaysiz_onizleme_doner_karmayla_onaylanir_ve_kur_karmayi_denetler(tmp_path):
    context = _context(tmp_path)
    source = _hooked_plugin(tmp_path / "kaynak")
    preview = _call("eklenti.onizle", {"kaynak": str(source)}, context)
    karma = preview["onizleme"]["karma"]  # type: ignore[index]
    assert isinstance(karma, str) and len(karma) == 64
    assert preview["onizleme"]["kancalar"] == ["Stop: true"]  # type: ignore[index]

    wrong = _call(
        "eklenti.kur", {"kaynak": str(source), "onay": True, "beklenen_karma": "0" * 64}, context
    )
    assert wrong["ok"] is False and "değişti" in str(wrong["metin"])
    assert _call(
        "eklenti.kur", {"kaynak": str(source), "onay": True, "beklenen_karma": karma}, context
    )["ok"]

    from fusion_cli.config import plugin_store

    hooks = plugin_store.plugins_dir() / "bicimci" / "hooks" / "hooks.json"
    hooks.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "kotu"}]}]}}),
        encoding="utf-8",
    )
    asked = _call("eklenti.guven", {"ad": "bicimci"}, context)
    assert asked["ok"] is False and asked["onay_gerekli"] is True
    assert asked["onizleme"]["kancalar"] == ["Stop: kotu"]  # type: ignore[index]
    yeni = asked["onizleme"]["karma"]  # type: ignore[index]
    assert plugin_store.installed_plugins()[0].status == plugin_store.STATUS_ACTIVE  # #392
    done = _call("eklenti.guven", {"ad": "bicimci", "onay": True, "beklenen_karma": yeni}, context)
    assert done["ok"] is True
    assert plugin_store.installed_plugins()[0].status == plugin_store.STATUS_ACTIVE


def _mcp_plugin(folder: Path) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "veri", "version": "0.1.0"}), encoding="utf-8"
    )
    (folder / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"db": {"command": "srv"}}}), encoding="utf-8"
    )
    return folder


async def test_masaustunde_eklenti_kapatma_ve_kaldirma_oturumdaki_mcp_yi_dusurur(
    tmp_path, monkeypatch
):
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.mcp_bridge import pool

    dropped: list[str] = []

    async def fake_drop(name: str) -> None:
        dropped.append(name)

    monkeypatch.setattr(pool, "drop_mcp_connection", fake_drop)
    session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "ev")
    source = str(_mcp_plugin(tmp_path / "kaynak"))
    installed = await session._extension_rpc("eklenti.kur", {"kaynak": source, "onay": True})
    assert installed["ok"] is True
    names = {s.name for s in session._state.config.mcp_servers}
    assert "plugin:veri:db" in names  # kurulumda aynı oturuma girer

    await session._extension_rpc("eklenti.etkinlik", {"ad": "veri", "etkin": False})
    assert "plugin:veri:db" not in {s.name for s in session._state.config.mcp_servers}
    assert dropped == ["plugin:veri:db"]

    await session._extension_rpc("eklenti.etkinlik", {"ad": "veri", "etkin": True})
    assert "plugin:veri:db" in {s.name for s in session._state.config.mcp_servers}
    await session._extension_rpc("eklenti.etkinlik", {"hepsi": True, "etkin": False})
    assert "plugin:veri:db" not in {s.name for s in session._state.config.mcp_servers}
    await session._extension_rpc("eklenti.etkinlik", {"hepsi": True, "etkin": True})
    # Claude `disable --all` her eklentiyi ayrı kapatır; `enable --all` yoktur (#409).
    await session._extension_rpc("eklenti.etkinlik", {"ad": "veri", "etkin": True})
    await session._extension_rpc("eklenti.kaldir", {"ad": "veri"})
    assert "plugin:veri:db" not in {s.name for s in session._state.config.mcp_servers}
    assert dropped == ["plugin:veri:db"] * 3


def test_repl_eklenti_kapatinca_mcp_kaydi_oturumdan_cikar(tmp_path):
    from fusion_cli.cli.repl.commands import build_registry
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    context = _context(tmp_path)
    state = ReplState(
        config=context.config, memory=null_memory(), root=context.root, home=context.home
    )
    command = build_registry(context.home, skills=lambda: state.capabilities).get("plugin")
    assert command is not None
    command.handler(state, f"kur {_mcp_plugin(tmp_path / 'kaynak')} --yes")
    assert "plugin:veri:db" in {s.name for s in state.config.mcp_servers}
    command.handler(state, "kapat veri")
    assert "plugin:veri:db" not in {s.name for s in state.config.mcp_servers}


def test_guncelle_dogrula_ve_pazar_guncelle_rpcleri(tmp_path):
    context = _context(tmp_path)
    source = _hooked_plugin(tmp_path / "kaynak")
    assert _call("eklenti.kur", {"kaynak": str(source), "onay": True}, context)["ok"]

    same = _call("eklenti.guncelle", {"ad": "bicimci"}, context)
    assert same["ok"] is True and same["guncel"] is True

    (source / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "yeni"}]}]}}),
        encoding="utf-8",
    )
    # Claude: sürüm aynıysa update hiçbir şey değiştirmez (#393).
    assert _call("eklenti.guncelle", {"ad": "bicimci"}, context)["guncel"] is True
    (source / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "bicimci", "version": "0.2.0"}), encoding="utf-8"
    )
    asked = _call("eklenti.guncelle", {"ad": "bicimci"}, context)
    assert asked["onay_gerekli"] is True
    assert asked["onizleme"]["kancalar"] == ["Stop: yeni"]  # type: ignore[index]
    karma = asked["onizleme"]["karma"]  # type: ignore[index]
    done = _call(
        "eklenti.guncelle", {"ad": "bicimci", "onay": True, "beklenen_karma": karma}, context
    )
    assert done["ok"] is True and done["yenile"] is True and done["guncel"] is False

    checked = _call("eklenti.dogrula", {"ad": "bicimci"}, context)
    assert checked["ok"] is True and checked["gecerli"] is True
    assert checked["butunluk"] == "etkin" and checked["hatalar"] == []
    assert _call("eklenti.dogrula", {"ad": "yok"}, context)["ok"] is False
    missing = _call("eklenti.pazar_guncelle", {"ad": "yok"}, context)
    assert missing["ok"] is False and "Pazar yok" in str(missing["metin"])


def test_pazar_ekle_kesfet_ve_kaldir_rpcleri(tmp_path):
    context = _context(tmp_path)
    market = tmp_path / "pazar"
    _hooked_plugin(market / "plugins" / "bicimci")
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "Ekip"},
                "plugins": [{"name": "bicimci", "source": "./plugins/bicimci"}],
            }
        ),
        encoding="utf-8",
    )

    added = _call("eklenti.pazar_ekle", {"kaynak": str(market)}, context)
    assert added["ok"] is True and added["pazarlar"][0]["ad"] == "ekip"  # type: ignore[index]
    found = _call("eklenti.kesfet", {}, context)
    assert found["eklentiler"] == [  # type: ignore[comparison-overlap]
        {"ad": "bicimci", "pazar": "ekip", "surum": "", "aciklama": "", "kurulu": False}
    ]
    assert _call("eklenti.pazar_guncelle", {"ad": "ekip"}, context)["ok"] is True
    removed = _call("eklenti.pazar_kaldir", {"ad": "ekip"}, context)
    assert removed["pazarlar"] == [] and removed["kaldirilan"] == []
    assert _call("eklenti.kesfet", {"pazar": "ekip"}, context)["ok"] is False
