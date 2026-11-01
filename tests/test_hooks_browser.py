"""`/hooks` tarayıcısı (#130): kaynak etiketi, seçilen kancanın tam metni ve tanım yeri,
sonda "All events"."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.cli.repl import hooks_browser
from fusion_cli.cli.repl.hooks_command import hooks
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config

_LONG = "python3 /uzun/yol/" + "x" * 80 + "/kanca.py"


def _set() -> HookSet:
    return HookSet(
        (
            HookCommand(HookEvent.STOP, "", "echo dur", 30.0, "proje", "/p/.claude/settings.json"),
            HookCommand(
                HookEvent.PRE_TOOL_USE,
                "Bash",
                _LONG,
                60.0,
                "kullanici",
                "/ev/.claude/settings.json",
            ),
            HookCommand(HookEvent.SESSION_START, "", "echo e", 5.0, "eklenti:deneme", "/e/h.json"),
            HookCommand(HookEvent.POST_TOOL_USE, "", "echo b", 5.0, "beceri:yaz", "/b/SKILL.md"),
        )
    )


def _state(tmp_path: Path, hook_set: HookSet) -> ReplState:
    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    state.hook_session = HookSession(root=tmp_path, loader=lambda: hook_set)
    return state


def test_secenekler_kaynak_etiketli_sonda_all_events():
    choices = hooks_browser.hook_choices(_set())
    assert [c.value for c in choices] == ["1", "2", "3", "4", "all"]
    assert choices[-1].label == "All events"
    labels = {c.label: c.description for c in choices[:-1]}
    assert labels["PreToolUse [Bash]"].endswith("kullanıcı ayarı")
    assert labels["Stop"].endswith("proje ayarı")
    assert labels["SessionStart"].endswith("eklenti: deneme")
    assert labels["PostToolUse"].endswith("oturum (beceri: yaz)")
    assert "…" in labels["PreToolUse [Bash]"]  # listede kısaltılır


def test_secilen_kanca_tam_metin_ve_tanim_yeri(tmp_path):
    state = _state(tmp_path, _set())
    numara = next(
        c.value for c in hooks_browser.hook_choices(_set()) if c.label == "PreToolUse [Bash]"
    )
    text = hooks(state, numara)
    assert _LONG in text
    assert "/ev/.claude/settings.json" in text
    assert "kullanıcı ayarı" in text


def test_all_events_tanimsiz_olaylari_da_listeler(tmp_path):
    text = hooks(_state(tmp_path, _set()), "all")
    assert "All events" in text
    assert "· Notification: 0 kanca" in text
    assert "· Stop: 1 kanca" in text
    assert "Setup: 0 kanca  (Fusion bu olayı tetiklemiyor)" in text


def test_argumansiz_numarali_liste_ve_gecersiz_numara(tmp_path):
    state = _state(tmp_path, _set())
    text = hooks(state, "")
    assert "1. " in text and "all. All events" in text and "/hooks <no>" in text
    assert hooks(state, "99").startswith("Kullanım: /hooks")


def test_beceri_oturum_kancasi_listede(tmp_path):
    state = _state(tmp_path, HookSet())
    session = state.hooks()
    session.add_session_commands(
        (HookCommand(HookEvent.STOP, "", "echo s", 5.0, "beceri:x", "/s/SKILL.md"),)
    )
    assert "oturum (beceri: x)" in hooks(state, "")
