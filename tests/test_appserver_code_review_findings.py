"""Masaüstünde `/code-review` bulguları kart olarak döner (#214, Claude Code ReportFindings)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli import session as cli_session

CEVAP = (
    "Bir hata var.\n```findings\n"
    '[{"file": "a.py", "line": 3, "summary": "sıfıra bölme", '
    '"failure_scenario": "n=0 → ZeroDivisionError", "verdict": "CONFIRMED"}]\n```'
)


@pytest.mark.asyncio
async def test_masaustu_code_review_bulgulari_kart_olarak_doner(tmp_path, monkeypatch):
    seen: list[str] = []

    async def fake_run_agent_task(task, _config, **_kwargs):
        seen.append(task)
        return SimpleNamespace(ok=True, final_text=CEVAP, messages=[], made_no_changes=True)

    monkeypatch.setattr(cli_session, "run_agent_task", fake_run_agent_task)
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        komut = await app._dispatch(
            Request("k1", "komut.calistir", {"ad": "code-review", "arguman": "high"})
        )
        gorev = komut["gorev"]
        assert "[bulgu-listesi]" in gorev
        sonuc = await app._dispatch(Request("t1", "tur.calistir", {"gorev": gorev}))
        assert sonuc["metin"] == "Bir hata var."
        assert sonuc["bulgular"][0]["file"] == "a.py"
        assert sonuc["bulgular"][0]["verdict"] == "CONFIRMED"
        duz = await app._dispatch(Request("t2", "tur.calistir", {"gorev": "merhaba"}))
        assert "bulgular" not in duz and "```findings" in duz["metin"]
    finally:
        await app.close()
