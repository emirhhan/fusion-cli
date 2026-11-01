"""`PostToolBatch` kancası (#90): araç grubu bitince, sonraki model çağrısından önce bir kez."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.hooks.events import HookEvent

from .fakes import model_result, tool_call
from .test_hooks_loop import _kanca, _kayit_kancasi, _oturum, _satirlar, _tur


def _iki_yazma(final: str = "bitti") -> list:
    return [
        model_result(
            tool_calls=[
                tool_call("write_file", path="a.txt", content="1"),
                tool_call("write_file", path="b.txt", content="2"),
            ]
        ),
        model_result(final),
    ]


async def test_grup_basina_bir_kez_tum_cagrilarla_calisir(monkeypatch, tmp_path: Path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(tmp_path, _kayit_kancasi(tmp_path, HookEvent.POST_TOOL_BATCH, kayit))
    outcome, _, _, _ = await _tur(monkeypatch, tmp_path, _iki_yazma(), session)
    (satir,) = _satirlar(kayit)
    assert satir["hook_event_name"] == "PostToolBatch"
    calls = satir["tool_calls"]
    assert [c["tool_name"] for c in calls] == ["Write", "Write"]
    assert all(c["tool_use_id"] and c["tool_response"] for c in calls)
    assert calls[0]["tool_input"]["file_path"].endswith("a.txt")
    assert outcome.final_text.endswith("bitti")


async def test_additional_context_sonraki_model_cagrisina_eklenir(monkeypatch, tmp_path: Path):
    body = (
        "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolBatch', "
        "'additionalContext': 'pytest koş'}}))\n"
    )
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.POST_TOOL_BATCH, body))
    outcome, _, _, _ = await _tur(monkeypatch, tmp_path, _iki_yazma(), session)
    notes = [m.content for m in outcome.messages if "PostToolBatch hook additional" in m.content]
    assert len(notes) == 1 and "pytest koş" in notes[0]


async def test_block_donguyu_sonraki_model_cagrisindan_once_durdurur(monkeypatch, tmp_path):
    body = "print(json.dumps({'decision': 'block', 'reason': 'önce testler'}))\n"
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.POST_TOOL_BATCH, body))
    outcome, provider, _, _ = await _tur(monkeypatch, tmp_path, _iki_yazma("çağrılmamalı"), session)
    assert "önce testler" in outcome.final_text
    assert outcome.final_text != "çağrılmamalı"
    assert provider.calls == 1
    assert any("önce testler" in m.content for m in outcome.messages if m.role == "user")
