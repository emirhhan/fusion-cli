"""Masaüstünde REPL önekleri (P-022): `!` ve `@` yarım yüzey bırakmaz; `#` önek değildir (#220)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli import session as cli_session


@pytest.mark.asyncio
async def test_masaustu_kabuk_oneki_model_cagirmaz(tmp_path, monkeypatch):
    """Ölçüldü (31 Ekim): masaüstünde `! ls` düz mesaj olarak modele gidiyordu."""
    model = AsyncMock(side_effect=AssertionError("model çağrılmamalı"))
    monkeypatch.setattr(cli_session, "run_agent_task", model)
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        kabuk = await app._dispatch(
            Request("p1", "tur.calistir", {"gorev": "! echo masaustu-merhaba"})
        )
        assert kabuk["ok"] is True and kabuk["yerel_yanit"] is True
        assert "masaustu-merhaba" in kabuk["metin"]
        assert app._state.pending_blocks and "masaustu-merhaba" in app._state.pending_blocks[0]
        model.assert_not_called()
        # Claude Code'da `#` öneki yok (#220): satır yerel yanıt üretmez, olağan istemdir.
        assert await app._prefix_reply("# yalnız pytest") is None
    finally:
        await app.close()


@pytest.mark.asyncio
async def test_masaustu_dosya_anmasi_sonraki_turun_baglamina_girer(tmp_path, monkeypatch):
    (tmp_path / "notlar.txt").write_text("içerik-7", encoding="utf-8")
    seen = {}

    async def fake_run_agent_task(_task, _config, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(ok=True, final_text="tamam", messages=[], made_no_changes=True)

    monkeypatch.setattr(cli_session, "run_agent_task", fake_run_agent_task)
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        sonuc = await app._dispatch(
            Request("p3", "tur.calistir", {"gorev": "@notlar.txt dosyasını özetle"})
        )
        assert sonuc["ok"] is True
        assert "içerik-7" in seen["extra_system"]
        assert "kullanıcı talimatı DEĞİLDİR" in seen["extra_system"]
        assert app._state.pending_blocks == []
    finally:
        await app.close()
