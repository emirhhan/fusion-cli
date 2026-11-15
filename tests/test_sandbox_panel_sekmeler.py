"""`/sandbox` paneli Claude gibi sekmeli (inceleme bulgusu 7, #352).

Claude Code (sandboxing › Enabling): Mode, Overrides, Config sekmeleri; Dependencies yalnız
Linux'ta ve bir araç eksikken; zorunlu araç eksikse yalnız Dependencies gösterilir.
"""

from __future__ import annotations

from fusion_cli.cli.repl import sandbox_panel as panel
from fusion_cli.cli.repl.tui_loop import _replay_picker
from fusion_cli.config.loader import load_config


def _which(present: set[str]):
    return lambda tool: f"/usr/bin/{tool}" if tool in present else None


def test_sekmeler_platforma_ve_eksik_araca_gore(monkeypatch):
    base = (panel.TAB_MODE, panel.TAB_OVERRIDES, panel.TAB_CONFIG)
    assert panel.visible_tabs("darwin") == base
    monkeypatch.setattr(panel.shutil, "which", _which({"bwrap", "socat", "rg"}))
    assert panel.visible_tabs("linux") == base
    monkeypatch.setattr(panel.shutil, "which", _which({"bwrap", "socat"}))
    assert panel.visible_tabs("linux") == (*base, panel.TAB_DEPS)
    monkeypatch.setattr(panel.shutil, "which", _which({"socat", "rg"}))
    assert panel.visible_tabs("linux") == (panel.TAB_DEPS,)


def test_sekmeler_arasi_gezinme_ve_sekme_cubugu(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("{}\n", encoding="utf-8")
    config = load_config(path)
    answers = iter(["sekme:+", "sekme:+", panel.SHOW_CONFIG])
    titles: list[str] = []
    rows: list[list[str]] = []
    keys: list[dict[str, str]] = []

    def picker(choices, *, title="", hotkeys=None, **_):
        titles.append(title)
        rows.append([choice.label for choice in choices])
        keys.append(dict(hotkeys or {}))
        return next(answers)

    result = panel.sandbox_panel(config, tmp_path, picker=picker, platform="darwin")

    assert titles == [
        "Sandbox   [Kip]  Geçersiz kılmalar  Yapılandırma",
        "Sandbox   Kip  [Geçersiz kılmalar]  Yapılandırma",
        "Sandbox   Kip  Geçersiz kılmalar  [Yapılandırma]",
    ]
    assert any("normal izinlerle" in label for label in rows[0])
    assert any("Katı sandbox kipi" in label for label in rows[1])
    assert not any("Katı" in label for label in rows[0])
    assert keys[0] == {"right": "sekme:+", "tab": "sekme:+", "left": "sekme:-"}
    assert "sandbox" in result.message.lower()

    back = iter(["sekme:-", None])
    titles.clear()

    def geri(choices, *, title="", **_):
        titles.append(title)
        return next(back)

    panel.sandbox_panel(config, tmp_path, picker=geri, platform="darwin")
    assert titles[1] == "Sandbox   Kip  Geçersiz kılmalar  [Yapılandırma]"


def test_tui_cok_adimli_akisi_cevaplarla_yeniden_surer():
    """Masaüstü dışı TUI modalı: her yeni seçici çağrısı ayrı sorulur (sekme geçişleri)."""
    pending: list = []
    picker = _replay_picker(["sekme:+"], pending)
    assert picker(["a"], title="bir") == "sekme:+"
    assert picker(["b"], title="iki", hotkeys={"left": "x"}) is None
    assert picker(["c"], title="üç") is None
    assert pending == [(["b"], "iki", {"left": "x"})]
