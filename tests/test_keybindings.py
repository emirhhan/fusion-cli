"""Özelleştirilebilir tuş bağları ve vim kipi (P-067)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from prompt_toolkit.enums import EditingMode

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.input import ReplInput, build_input_bindings, prompt_fragments
from fusion_cli.cli.repl.keybinding_commands import keybindings_command, vim_command
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.tui import FusionTui, format_status
from fusion_cli.config import keybindings
from fusion_cli.config.loader import load_config
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory


def _binding_keys(kb) -> set[tuple[str, ...]]:
    return {tuple(str(getattr(k, "value", k)) for k in b.keys) for b in kb.bindings}


def test_varsayilan_tablo_dosyasiz_yuklenir(tmp_path: Path):
    keymap = keybindings.load_keymap(tmp_path / "yok.json")
    assert (
        keymap.bindings("tui")["escape"] == "kes"
        and keymap.bindings("giris")["s-tab"] == "kip_dongusu"
    )
    assert keymap.warnings == ()


def test_kullanici_dosyasi_ezer_null_kaldirir_bilinmeyen_uyarir(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text(
        json.dumps(
            {
                "tui": {
                    "c-q": None,
                    "c-g": "kes",
                    "f2": "komut:status",
                    "enter": "cik",
                    "c-x": "ucmak",
                },
                "giris": {"c-t": "kip_dongusu"},
                "baska": {},
            }
        ),
        encoding="utf-8",
    )
    keymap = keybindings.load_keymap(path)
    tui = keymap.bindings("tui")
    assert "c-q" not in tui and tui["c-g"] == "kes" and tui["f2"] == "komut:status"
    assert tui["c-c"] == "kes_temizle_cik"  # varsayılan korunur
    assert keymap.bindings("giris")["c-t"] == "kip_dongusu"
    assert any("yapısal" in w for w in keymap.warnings)
    assert any("ucmak" in w for w in keymap.warnings)
    assert any("baska" in w for w in keymap.warnings)
    assert not keybindings.has_changed(keymap)
    path.write_text("{}", encoding="utf-8")
    import os

    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
    assert keybindings.has_changed(keymap)


def test_bozuk_dosya_oturumu_dusurmez(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text("{bozuk", encoding="utf-8")
    keymap = keybindings.load_keymap(path)
    assert keymap.bindings("tui")["escape"] == "kes" and keymap.warnings


def test_tui_baglari_tablodan_kurulur_ve_yeniden_baglanir(tmp_path: Path):
    path = tmp_path / "keybindings.json"
    path.write_text(json.dumps({"tui": {"c-d": None, "f2": "komut:status"}}), encoding="utf-8")
    olaylar = []
    tui = FusionTui(
        on_submit=olaylar.append,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
        keymap=keybindings.load_keymap(path),
    )
    keys = _binding_keys(tui.application.key_bindings)
    assert ("f2",) in keys and ("c-d",) not in keys and ("c-c",) in keys
    # Yapısal bağlar yerinde.
    assert ("up",) in keys and ("c-m",) in keys  # Enter prompt_toolkit'te c-m
    tui.rebind(keybindings.load_keymap(tmp_path / "yok.json"))
    keys = _binding_keys(tui.application.key_bindings)
    assert ("c-d",) in keys and ("f2",) not in keys
    tui.set_vim(True)
    assert tui.application.editing_mode is EditingMode.VI
    assert "· vim" in format_status("auto", "agent", vim=True)


def test_giris_baglari_tablodan_ve_komut_bagi(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    reader = ReplInput(tmp_path / "h", [], mode=ApprovalMode.AUTO)
    path = tmp_path / "keybindings.json"
    path.write_text(json.dumps({"giris": {"c-t": "komut:help", "c-v": None}}), encoding="utf-8")
    kb = build_input_bindings(reader, keybindings.load_keymap(path))
    keys = _binding_keys(kb)
    assert ("c-t",) in keys and ("c-v",) not in keys and ("s-tab",) in keys
    assert "vim" in prompt_fragments(ApprovalMode.AUTO, vim=True)
    assert "vim" not in prompt_fragments(ApprovalMode.AUTO)


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_vim_komutu_tersler_ve_kalicilastirir(state: ReplState, tmp_path: Path):
    registry = build_registry()
    assert registry.get("vim") is not None and registry.get("keybindings") is not None
    assert "açık" in vim_command(state, "")
    assert state.config.runtime.vim_mode is True
    assert load_config(tmp_path / "config.yaml").runtime.vim_mode is True
    assert "kapalı" in vim_command(state, "off")
    assert "Kullanım" in vim_command(state, "belki")


def test_keybindings_komutu_ornek_dosya_yazar_ve_listeler(
    state: ReplState, tmp_path: Path, monkeypatch
):
    path = tmp_path / "ev" / "keybindings.json"
    monkeypatch.setattr(keybindings, "keybindings_path", lambda: path)
    out = keybindings_command(state, "")
    assert path.is_file() and str(path) in out and "[tui]" in out and "escape" in out


def test_vim_kipinde_escape_insert_ten_normale_gecer_kesmez():
    """Ölçüldü (31 Ekim): `escape: kes` uygulama düzeyinde eager bağlıydı; vi kipinde Esc her
    zaman `_cancel_or_interrupt`'a gidiyor, vi_state INSERT'te kalıyordu (NORMAL'e geçilemiyordu).
    Artık INSERT kipinde (seçici açık değilken) bağ devre dışı: prompt_toolkit'in vi bağı çalışır.
    """
    from prompt_toolkit.application.current import set_app
    from prompt_toolkit.key_binding.vi_state import InputMode
    from prompt_toolkit.keys import Keys

    tui = FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )
    escape = [b for b in tui.application.key_bindings.bindings if tuple(b.keys) == (Keys.Escape,)]
    assert len(escape) == 1
    with set_app(tui.application):
        assert escape[0].filter()  # emacs: Esc keser
        tui.set_vim(True)
        tui.application.vi_state.input_mode = InputMode.INSERT
        assert not escape[0].filter()  # vi INSERT: Esc NORMAL'e geçer, kesmez
        tui.application.vi_state.input_mode = InputMode.NAVIGATION
        assert escape[0].filter()  # vi NORMAL: Esc keser
        tui.application.vi_state.input_mode = InputMode.INSERT
        tui._mode = "choice"
        assert escape[0].filter()  # seçici açıkken Esc her kipte iptal
        tui.set_vim(False)
        tui._mode = "idle"
        assert escape[0].filter()
