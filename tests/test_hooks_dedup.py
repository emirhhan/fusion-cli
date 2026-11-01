"""Kanca tekilleştirmesi (#94): aynı işleyici ayar dosyaları arasında bir kez çalışır."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config.hook_parse import parse_hooks_block
from fusion_cli.core.hooks.events import HookEvent, HookSet


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


def _parse(handlers: list[dict[str, object]], source: str = "kullanici") -> HookSet:
    block = {"PreToolUse": [{"matcher": "Bash", "hooks": handlers}]}
    commands, skipped = parse_hooks_block(block, source=source, path=Path(f"{source}.json"))
    assert not skipped
    return HookSet(commands)


def _targets(hooks: HookSet) -> list[tuple[str, tuple[str, ...] | None, str]]:
    found = hooks.for_event(HookEvent.PRE_TOOL_USE, ("Bash",))
    return [(c.command, c.args, c.condition) for c in found]


def test_ayni_komut_farkli_args_iki_kanca_olarak_calisir():
    hooks = _parse(
        [
            {"type": "command", "command": "node", "args": ["a.js"]},
            {"type": "command", "command": "node", "args": ["b.js"]},
        ]
    )
    assert _targets(hooks) == [("node", ("a.js",), ""), ("node", ("b.js",), "")]


def test_ayni_komut_farkli_if_kosulu_dusmez():
    hooks = _parse(
        [
            {"type": "command", "command": "denetle", "if": "Bash(git *)"},
            {"type": "command", "command": "denetle", "if": "Bash(rm *)"},
        ]
    )
    assert [condition for *_, condition in _targets(hooks)] == ["Bash(git *)", "Bash(rm *)"]


def test_ayni_isleyici_iki_ayar_dosyasinda_bir_kez_calisir():
    handler = {"type": "command", "command": "denetle"}
    user = _parse([handler], "kullanici")
    project = _parse([handler], "proje")
    merged = HookSet((*user.commands, *project.commands))
    assert len(merged.for_event(HookEvent.PRE_TOOL_USE, ("Bash",))) == 1


def test_beceri_ve_eklenti_kopyasi_ayri_kalir():
    handler = {"type": "command", "command": "denetle"}
    user = _parse([handler], "kullanici")
    skill = _parse([handler], "beceri:bicim")
    plugin = _parse([handler], "eklenti:denetim")
    merged = HookSet((*user.commands, *skill.commands, *plugin.commands))
    found = merged.for_event(HookEvent.PRE_TOOL_USE, ("Bash",))
    assert [c.source for c in found] == ["kullanici", "beceri:bicim", "eklenti:denetim"]


def test_filechanged_ve_stopfailure_dar_eslesme_kurali():
    # Claude (#89): bu iki olayda düz liste yalnız harf/rakam/`_`/`|`; tire, boşluk ya da
    # virgül eşleştiriciyi düzenli ifade yoluna (çapasız) sokar.
    from fusion_cli.core.hooks.matcher import matcher_matches

    assert matcher_matches("rate_limit|server_error", ("server_error",), narrow=True)
    # Virgül ayırıcı değildir: "a,b" düzenli ifadesi "a" adıyla eşleşmez.
    assert not matcher_matches("rate_limit,server_error", ("server_error",), narrow=True)
    assert matcher_matches("rate_limit,server_error", ("server_error",))
    # Tire düzenli ifade yolu: çapasız arama alt dizeyi de yakalar.
    assert matcher_matches("my-file", ("xmy-filey",), narrow=True)
    assert not matcher_matches("my-file", ("xmy-filey",))
    block = {
        "StopFailure": [
            {"matcher": "a,server_error", "hooks": [{"type": "command", "command": "k"}]}
        ]
    }
    commands, _ = parse_hooks_block(block, source="kullanici", path=Path("s.json"))
    assert HookSet(commands).for_event(HookEvent.STOP_FAILURE, ("server_error",)) == ()
