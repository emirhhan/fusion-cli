"""Claude Code `~/.claude/keybindings.json` biçimi (#194), düzenleme eylemleri (#216),
kuyruğun aynı tura verilmesi ve geri alınması (#190)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.cli.repl import input_actions, queue_steer
from fusion_cli.cli.repl.tui import FusionTui
from fusion_cli.config import claude_keybindings as ck
from fusion_cli.config import keybindings
from fusion_cli.core.steering import SteeringQueue


def _keys(kb) -> set[tuple[str, ...]]:
    return {tuple(str(getattr(k, "value", k)) for k in b.keys) for b in kb.bindings}


def test_tus_yazimi_claude_bicimi_prompt_toolkit_adina_cevrilir():
    assert ck.keystroke_to_key("ctrl+k") == "c-k"
    assert ck.keystroke_to_key("Ctrl+K") == "c-k"
    assert ck.keystroke_to_key("shift+tab") == "s-tab"
    assert ck.keystroke_to_key("meta+p") == "escape p"
    assert ck.keystroke_to_key("ctrl+x ctrl+e") == "c-x c-e"
    assert ck.keystroke_to_key("esc") == "escape"
    assert ck.keystroke_to_key("ctrl+home") == "c-home"
    assert ck.keystroke_to_key("shift+k") == "K"
    assert ck.keystroke_to_key("f5") == "f5"
    assert ck.keystroke_to_key("cmd+k") is None
    assert ck.keystroke_to_key("hyper+k") is None


def test_claude_dosyasi_eski_dosyanin_ustune_uygulanir(tmp_path: Path):
    claude = tmp_path / "claude" / "keybindings.json"
    claude.parent.mkdir()
    claude.write_text(
        json.dumps(
            {
                "$schema": ck.SCHEMA_URL,
                "bindings": [
                    {
                        "context": "Chat",
                        "bindings": {
                            "ctrl+e": "chat:externalEditor",
                            "ctrl+s": None,
                            "meta+g": "command:compact",
                            "ctrl+c": "chat:stash",
                            "ctrl+y": "chat:fastMode",
                        },
                    },
                    {"context": "Task", "bindings": {"ctrl+x ctrl+b": None}},
                    {"context": "Scroll", "bindings": {"ctrl+u": "scroll:pageUp"}},
                    {"context": "Bilinmez", "bindings": {}},
                    {"context": "Confirmation", "bindings": {"y": "confirm:yes"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    legacy = tmp_path / "fusion" / "keybindings.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"tui": {"f2": "komut:status"}}), encoding="utf-8")
    keymap = keybindings.load_keymap(legacy, claude)
    tui, giris = keymap.bindings("tui"), keymap.bindings("giris")
    assert tui["c-e"] == "dis_editor" and giris["c-e"] == "dis_editor"
    assert "c-s" not in tui and "c-s" not in giris
    assert tui["escape g"] == "komut:compact"
    assert "c-x c-b" not in tui and tui["c-b"] == "arka_plana_al"
    assert tui["c-u"] == "sayfa_yukari" and "c-u" not in giris
    assert tui["f2"] == "komut:status"  # eski dosya takma ad olarak okunur
    assert tui["c-c"] == "kes_temizle_cik"  # ayrılmış tuş bağlanamaz
    warnings = " | ".join(keymap.warnings)
    assert "ayrılmış" in warnings and "chat:fastMode" in warnings
    assert "Bilinmez" in warnings and "kullanımdan kalktı" in warnings
    assert "confirm:yes" not in warnings  # bilinen bağlam, Fusion'da yüzeyi yok
    assert not keybindings.has_changed(keymap)
    claude.write_text(json.dumps({"bindings": []}), encoding="utf-8")
    import os

    os.utime(claude, (claude.stat().st_atime, claude.stat().st_mtime + 5))
    assert keybindings.has_changed(keymap)
    reloaded = keybindings.reload_keymap(keymap)
    assert "c-e" not in reloaded.bindings("tui") and reloaded.claude_path == claude


def test_varsayilan_yol_claude_config_dir_ve_iskelet(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cc"))
    path = keybindings.write_claude_file()
    assert path == tmp_path / "cc" / "keybindings.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["$schema"] == ck.SCHEMA_URL and body["bindings"] == []
    assert keybindings.load_keymap().claude_path == path


def test_varsayilanlar_claude_ile_ayni():
    tui = keybindings.load_keymap(Path("/yok/keybindings.json")).bindings("tui")
    assert tui["c-x c-s"] == "simdi_gonder" and tui["c-g"] == "dis_editor"
    assert tui["c-x c-e"] == "dis_editor" and tui["c-_"] == "geri_al"
    assert tui["c-s"] == "sakla" and tui["c-l"] == "yeniden_ciz"
    assert tui["c-x c-b"] == "arka_plana_al"
    # Home/End girdide imleci taşır; kaydırma Ctrl+Home/Ctrl+End (Claude Scroll bağlamı).
    assert "home" not in tui and "end" not in tui and tui["c-home"] == "en_bas"


def test_tui_chord_baglari_kurulur():
    tui = FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
        keymap=keybindings.load_keymap(Path("/yok/keybindings.json")),
    )
    keys = _keys(tui.application.key_bindings)
    assert ("c-x", "c-e") in keys and ("c-x", "c-s") in keys and ("c-g",) in keys


class _Buffer:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.cursor_position = len(text)

    def reset(self) -> None:
        self.text, self.cursor_position = "", 0


def test_ctrl_s_taslagi_saklar_ve_bos_girdide_geri_getirir():
    stash, buffer = input_actions.PromptStash(), _Buffer("yarım istem")
    buffer.cursor_position = 3
    assert stash.toggle(buffer) and buffer.text == ""
    assert stash.toggle(buffer) and buffer.text == "yarım istem"
    assert buffer.cursor_position == 3
    assert not stash.toggle(_Buffer())


def test_kuyruk_ayni_tura_verilir_tuketilmeyen_geri_doner():
    bridge = queue_steer.SteerBridge()
    assert not bridge.offer("şunu da yap")  # tur yok
    queue = bridge.begin()
    assert isinstance(queue, SteeringQueue)
    assert bridge.offer("birinci") and bridge.offer("ikinci")
    assert not bridge.offer("/status") and not bridge.offer("!ls") and not bridge.offer("@a.py")
    queue.drain()  # motor ilk iki mesajı okudu
    assert bridge.offer("üçüncü") and bridge.pending
    consumed, leftover = bridge.end()
    assert consumed == ["birinci", "ikinci"] and leftover == ["üçüncü"]
    assert not bridge.active


def test_up_ile_geri_alma_modele_gitmeyeni_cikarir():
    bridge = queue_steer.SteerBridge()
    bridge.begin()
    bridge.offer("geri al beni")
    assert bridge.take_back() == ["geri al beni"]
    assert bridge.end() == ([], [])
    assert input_actions.take_back_text(["a", "b"], "taslak") == "a\nb\ntaslak"
    assert input_actions.take_back_text(["a"], "") == "a"
