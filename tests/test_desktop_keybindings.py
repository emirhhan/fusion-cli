"""Masaüstü kısayolları: `keybindings.json` `masaustu` bağlamı ve `kisayol.*` uçları (P-046)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver import keybindings_rpc
from fusion_cli.config import keybindings
from fusion_cli.config.desktop_keys import (
    CONTEXT_DESKTOP,
    desktop_key_data,
    desktop_key_problem,
    normalize_desktop_key,
)
from fusion_cli.config.keybinding_edit import bind_action, reset_action, unbind_action
from fusion_cli.core.errors import ConfigError

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mod+K", "mod+k"),
        ("shift+mod+p", "mod+shift+p"),
        ("alt+ctrl+mod+1", "mod+ctrl+alt+1"),
        ("mod+,", "mod+,"),
        ("mod++", "mod++"),
        ("mod+shift+/", "mod+/"),
        ("F5", "f5"),
        ("mod+ArrowUp", "mod+arrowup"),
        ("mod+", None),
        ("mod+mod+k", None),
        ("super+k", None),
        ("mod+kk", None),
        ("", None),
    ],
)
def test_masaustu_tus_yazimi_kanoniklesir(raw: str, expected: str | None):
    assert normalize_desktop_key(raw) == expected


def test_degistiricisiz_ve_sistem_tuslari_baglanamaz():
    assert desktop_key_problem("k") and desktop_key_problem("shift+k")
    assert desktop_key_problem("mod+c") and desktop_key_problem("mod+q")
    assert desktop_key_problem("f5") is None and desktop_key_problem("alt+k") is None


def test_varsayilan_tablo_gecerli_ve_eylemleri_etiketli():
    data = desktop_key_data()
    for key, action in data.defaults.items():
        assert normalize_desktop_key(key) == key and desktop_key_problem(key) is None, key
        assert action in data.labels, action
    assert {"palet", "yeni_sohbet", "ayarlar", "kenar_cubugu", "terminal"} <= set(
        data.defaults.values()
    )
    assert data.defaults["mod+1"] == "sohbet_1" and data.defaults["mod+9"] == "sohbet_9"


def test_arayuz_ayni_veri_dosyasini_ice_aktarir():
    """Tek kaynak: TS tarafı Python paket verisini doğrudan içe aktarır (kopya yok)."""
    source = (REPO / "app/src/shortcuts/keys.ts").read_text(encoding="utf-8")
    assert "src/fusion_cli/config/data/masaustu-kisayollari.json" in source


def test_masaustu_baglami_terminal_yukleyicisinde_uyari_uretmez(tmp_path: Path):
    """Ölçüldü (31 Ekim): `masaustu` bağlamı eklenmeden önce yükleyici `bilinmeyen bağlam` derdi."""
    path = tmp_path / "keybindings.json"
    path.write_text(
        json.dumps({"masaustu": {"Mod+T": "terminal", "mod+j": None, "k": "palet", "mod+e": "u"}}),
        encoding="utf-8",
    )
    keymap = keybindings.load_keymap(path)
    table = keymap.bindings(CONTEXT_DESKTOP)
    assert table["mod+t"] == "terminal" and "mod+j" not in table and table["mod+k"] == "palet"
    assert not any("bilinmeyen bağlam" in warning for warning in keymap.warnings)
    assert any("masaustu.k:" in warning for warning in keymap.warnings)
    assert any("'u'" in warning for warning in keymap.warnings)
    # Terminal bağlamları etkilenmez.
    assert keymap.bindings("tui")["escape"] == "kes"
    assert any(line == "[masaustu]" for line in keybindings.describe(keymap))


def test_eylemi_tusa_bagla_eski_tusu_kaldirir_ve_dosyada_fark_tutar(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text(json.dumps({"tui": {"c-q": None}}), encoding="utf-8")
    assert bind_action(path, CONTEXT_DESKTOP, "terminal", "mod+shift+t", force=False).ok
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["masaustu"] == {"mod+j": None, "mod+shift+t": "terminal"}
    assert raw["tui"] == {"c-q": None}  # diğer bağlam korunur
    table = keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)
    assert table["mod+shift+t"] == "terminal" and "mod+j" not in table


def test_dolu_tus_cakisma_doner_zorla_devralir(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    result = bind_action(path, CONTEXT_DESKTOP, "terminal", "mod+k", force=False)
    assert not result.ok and result.conflict == "palet" and not path.exists()
    assert bind_action(path, CONTEXT_DESKTOP, "terminal", "mod+k", force=True).ok
    table = keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)
    assert table["mod+k"] == "terminal" and "palet" not in table.values()


def test_kaldir_ve_varsayilana_don(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    assert unbind_action(path, CONTEXT_DESKTOP, "kenar_cubugu").ok
    assert "kenar_cubugu" not in keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP).values()
    assert reset_action(path, CONTEXT_DESKTOP, "kenar_cubugu").ok
    assert keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)["mod+b"] == "kenar_cubugu"
    bind_action(path, CONTEXT_DESKTOP, "palet", "mod+shift+k", force=False)
    assert reset_action(path, CONTEXT_DESKTOP, None).ok
    assert "masaustu" not in json.loads(path.read_text(encoding="utf-8"))


def test_gecersiz_tus_ve_eylem_reddedilir(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    assert bind_action(path, CONTEXT_DESKTOP, "terminal", "mod+c", force=False).problem
    assert bind_action(path, CONTEXT_DESKTOP, "ucmak", "mod+e", force=False).problem
    assert bind_action(path, CONTEXT_DESKTOP, "komut:status", "mod+e", force=False).ok


def test_bozuk_dosyanin_ustune_yazilmaz(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text("{bozuk", encoding="utf-8")
    with pytest.raises(ConfigError):
        bind_action(path, CONTEXT_DESKTOP, "terminal", "mod+t", force=False)
    assert path.read_text(encoding="utf-8") == "{bozuk"


def test_rpc_liste_ata_cakisma_ve_hata(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    listing = keybindings_rpc.list_bindings(path=path)
    assert listing["ok"] and listing["baglar"]["mod+k"] == "palet"
    assert {"ad": "palet", "etiket": "Komut paletini aç"} in listing["eylemler"]
    conflict = keybindings_rpc.assign({"eylem": "terminal", "tus": "mod+k"}, path=path)
    assert conflict["ok"] is False and conflict["cakisma"] == "palet"
    assert "Komut paletini aç" in conflict["metin"]
    done = keybindings_rpc.assign({"eylem": "terminal", "tus": "mod+k", "zorla": True}, path=path)
    assert done["ok"] and done["baglar"]["mod+k"] == "terminal"
    assert keybindings_rpc.remove({"eylem": "terminal"}, path=path)["ok"]
    assert keybindings_rpc.reset({}, path=path)["baglar"]["mod+j"] == "terminal"
    assert keybindings_rpc.assign({"eylem": "terminal"}, path=path)["ok"] is False
    assert keybindings_rpc.reset({"eylem": 3}, path=path)["ok"] is False
    path.write_text("[]", encoding="utf-8")
    broken = keybindings_rpc.assign({"eylem": "terminal", "tus": "mod+t"}, path=path)
    assert broken["ok"] is False and "üstüne yazılmadı" in broken["metin"]


def test_rpc_terminal_uyarilarini_masaustune_tasimaz(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text(json.dumps({"tui": {"c-x": "ucmak"}, "masaustu": {"k": "palet"}}), "utf-8")
    warnings = keybindings_rpc.list_bindings(path=path)["uyarilar"]
    assert warnings and all(warning.startswith("masaustu.") for warning in warnings)


async def test_oturum_kisayol_isteklerini_dagitir(tmp_path: Path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    target = tmp_path / "keybindings.json"
    monkeypatch.setattr(keybindings_rpc, "keybindings_path", lambda: target)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    await session.handle(Request("k1", "kisayol.ata", {"eylem": "palet", "tus": "mod+shift+k"}))
    result = next(
        json.loads(line)["veri"] for line in reversed(lines) if json.loads(line).get("id") == "k1"
    )
    assert result["ok"] and result["baglar"]["mod+shift+k"] == "palet"
    assert json.loads(target.read_text(encoding="utf-8"))["masaustu"]["mod+k"] is None


def test_devredilen_tusu_varsayilana_donmek_cakisma_sorar_zorla_geri_alir(tmp_path: Path):
    """Ölçüldü (31 Ekim): Terminal mod+k'yı devralınca paletin `sifirla`sı ok:true dönüp hiçbir
    şey yapmıyordu (dosya {mod+j: null, mod+k: terminal} kalıyordu)."""
    path = tmp_path / "keybindings.json"
    assert bind_action(path, CONTEXT_DESKTOP, "terminal", "mod+k", force=True).ok
    result = reset_action(path, CONTEXT_DESKTOP, "palet")
    assert not result.ok and result.conflict == "terminal" and result.key == "mod+k"
    assert keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)["mod+k"] == "terminal"
    assert reset_action(path, CONTEXT_DESKTOP, "palet", force=True).ok
    table = keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)
    assert table["mod+k"] == "palet" and "terminal" not in table.values()


def test_rpc_sifirla_cakismayi_tusla_doner(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    keybindings_rpc.assign({"eylem": "terminal", "tus": "mod+k", "zorla": True}, path=path)
    conflict = keybindings_rpc.reset({"eylem": "palet"}, path=path)
    assert conflict["ok"] is False and conflict["cakisma"] == "terminal"
    assert conflict["tus"] == "mod+k" and "mod+k" in conflict["metin"]
    done = keybindings_rpc.reset({"eylem": "palet", "zorla": True}, path=path)
    assert done["ok"] and done["baglar"]["mod+k"] == "palet"


@pytest.mark.parametrize("key", ["ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+a", "ctrl+w"])
def test_ctrl_yazimi_ayrilmis_tus_korumasini_asamaz(tmp_path: Path, key: str):
    """Ölçüldü (31 Ekim): Windows/Linux'ta `ctrl` = `mod` olduğu hâlde `ctrl+c` kabul ediliyordu;
    global dinleyici Ctrl+C'yi yutup kopyalamayı bozuyordu."""
    assert desktop_key_problem(key)
    assert bind_action(tmp_path / "k.json", CONTEXT_DESKTOP, "terminal", key, force=True).problem
    assert (
        keybindings_rpc.assign({"eylem": "terminal", "tus": key}, path=tmp_path / "k.json")["ok"]
        is False
    )


def test_elle_yazilan_ctrl_sistem_tusu_yuklenmez(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text(json.dumps({"masaustu": {"ctrl+c": "terminal"}}), encoding="utf-8")
    keymap = keybindings.load_keymap(path)
    assert "ctrl+c" not in keymap.bindings(CONTEXT_DESKTOP)
    assert any("masaustu.ctrl+c:" in warning for warning in keymap.warnings)


def test_windowsta_ctrl_ve_mod_ayni_tus_sayilir(tmp_path: Path):
    """Ölçüldü (31 Ekim): Windows'ta `ctrl+k`, `mod+k` ile aynı tuşken çakışma sorulmuyordu."""
    path = tmp_path / "keybindings.json"
    other = bind_action(path, CONTEXT_DESKTOP, "terminal", "ctrl+k", force=False, mac=False)
    assert not other.ok and other.conflict == "palet"
    assert bind_action(path, CONTEXT_DESKTOP, "terminal", "ctrl+k", force=False, mac=True).ok
    path.unlink()
    assert bind_action(path, CONTEXT_DESKTOP, "terminal", "ctrl+k", force=True, mac=False).ok
    table = keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)
    assert table["ctrl+k"] == "terminal" and "mod+k" not in table
    # Paletin varsayılana dönüşü de aynı fiziksel tuşu tutan bağı çakışma sayar.
    reset = reset_action(path, CONTEXT_DESKTOP, "palet", mac=False)
    assert not reset.ok and reset.conflict == "terminal" and reset.key == "ctrl+k"
    assert reset_action(path, CONTEXT_DESKTOP, "palet", force=True, mac=False).ok
    table = keybindings.load_keymap(path).bindings(CONTEXT_DESKTOP)
    assert table["mod+k"] == "palet" and "ctrl+k" not in table


def test_turkce_buyuk_i_tek_harfe_kanoniklesir(tmp_path: Path):
    """Ölçüldü (31 Ekim): `"İ".lower()` iki karakterdir (i + U+0307); ⌘⇧İ geçersiz sayılıyordu."""
    assert normalize_desktop_key("mod+shift+İ") == "mod+shift+i"
    assert keybindings.normalize_key(CONTEXT_DESKTOP, "Mod+Shift+İ") == ("mod+shift+i", None)
    assert (
        keybindings_rpc.assign({"eylem": "palet", "tus": "mod+shift+İ"}, path=tmp_path / "k")[
            "baglar"
        ]["mod+shift+i"]
        == "palet"
    )
