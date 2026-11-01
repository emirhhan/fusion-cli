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
        # Claude Code (#219): çıktı bağlama girince model kendiliğinden yanıtlar (arayüz turu).
        assert "echo masaustu-merhaba" in kabuk["gorev"]
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


@pytest.mark.asyncio
async def test_masaustu_respond_to_bash_commands_false_yalniz_baglam(tmp_path, monkeypatch):
    import json

    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"respondToBashCommands": False}), encoding="utf-8"
    )
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        kabuk = await app._dispatch(Request("p2", "tur.calistir", {"gorev": "! echo sessiz"}))
        assert "gorev" not in kabuk and "sessiz" in kabuk["metin"]
    finally:
        await app.close()


@pytest.mark.asyncio
async def test_masaustu_kabuk_ciktisi_komut_surerken_olayla_akar(tmp_path):
    import json

    lines: list[str] = []
    app = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")
    try:
        kabuk = await app._dispatch(
            Request("p4", "tur.calistir", {"gorev": "! echo akan-1; echo akan-2"})
        )
        assert kabuk["ok"] is True
        events = [json.loads(line)["veri"] for line in lines if "KabukCiktisi" in line]
        parts = "".join(event.get("parca", "") for event in events)
        assert "akan-1" in parts and "akan-2" in parts
        assert events[-1].get("bitti") is True
        assert all(event["komut"] == "echo akan-1; echo akan-2" for event in events)
    finally:
        await app.close()


@pytest.mark.asyncio
async def test_masaustu_tuketilmeyen_yonlendirme_tur_sonunda_geri_doner(tmp_path, monkeypatch):
    """Claude Code (#190): tur biterken kuyrukta kalan mesaj tuşa basmadan sıradaki tura gider."""

    async def fake_run_agent_task(_task, _config, **kwargs):
        kwargs["steering"].push("bunu da ekle")  # son araç çağrısından sonra geldi
        return SimpleNamespace(ok=True, final_text="tamam", messages=[], made_no_changes=True)

    monkeypatch.setattr(cli_session, "run_agent_task", fake_run_agent_task)
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        sonuc = await app._dispatch(Request("p5", "tur.calistir", {"gorev": "işi yap"}))
        assert sonuc["kalan_yonlendirme"] == ["bunu da ekle"]
        assert app._steering_leftover == []  # bir kez teslim edilir
    finally:
        await app.close()
