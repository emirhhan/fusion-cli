"""`/görsel`: sohbetin içinden görsel üretme komutu."""

from __future__ import annotations

import pytest

from fusion_cli.appserver import image_chat
from fusion_cli.appserver.image_chat import ImageCommand, parse_image_command, run_image_command

from .fakes import make_config


@pytest.mark.parametrize(
    ("task", "prompt", "aspect"),
    [
        ("/görsel gün batımında bir dağ evi", "gün batımında bir dağ evi", "1:1"),
        ("/gorsel kedi --oran 16:9", "kedi", "16:9"),
        ("/GÖRSEL  kedi --oran=9:16  yağmurda", "kedi   yağmurda".replace("   ", " "), "9:16"),
        ("/görsel", "", "1:1"),
        ("  /görsel   ", "", "1:1"),
    ],
)
def test_komut_ayristirilir(task, prompt, aspect):
    command = parse_image_command(task)
    assert command is not None
    assert " ".join(command.prompt.split()) == prompt and command.aspect == aspect


@pytest.mark.parametrize(
    "task", ["merhaba", "bir görsel çiz", "/model", "/görselleştir kedi", "x /görsel"]
)
def test_komut_olmayanlar_modele_gider(task):
    assert parse_image_command(task) is None


async def test_bos_istem_kullanim_gosterir_ve_sirketle_konusmaz(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("sağlayıcıya gidilmemeli")

    monkeypatch.setattr(image_chat, "create_image", forbidden)
    ok, text = await run_image_command(make_config(), ImageCommand(prompt=""))
    assert ok is False and "/görsel" in text and "--oran" in text


async def test_basarili_sonuc_markdown_gorsel_ve_kunye_doner(monkeypatch, tmp_path):
    dosya = tmp_path / "kedi [1].png"
    seen = {}

    async def fake(config, data):
        seen.update(data)
        return {
            "ok": True,
            "saglayici": "NVIDIA FLUX",
            "dosyalar": [{"yol": str(dosya), "genislik": 1024, "yukseklik": 1024}],
        }

    monkeypatch.setattr(image_chat, "create_image", fake)
    ok, text = await run_image_command(
        make_config(), ImageCommand(prompt="kırmızı [kedi]", aspect="16:9")
    )
    assert ok is True and seen == {"istem": "kırmızı [kedi]", "oran": "16:9"}
    assert f"(<{dosya}>)" in text and "![kırmızı (kedi)]" in text  # köşeli ayraç kaçar
    # ChatGPT gibi yalnız görsel: sağlayıcı, boyut ya da galeri notu yok.
    assert text == f"![kırmızı (kedi)](<{dosya}>)"
    for note in ("NVIDIA", "1024", "Galeri", "galeri"):
        assert note not in text


async def test_hatalar_kullaniciya_aynen_gosterilir(monkeypatch):
    async def failing(config, data):
        return {"ok": False, "metin": "Görsel üretebilen bağlı sağlayıcı yok."}

    monkeypatch.setattr(image_chat, "create_image", failing)
    ok, text = await run_image_command(make_config(), ImageCommand(prompt="kedi"))
    assert ok is False and "sağlayıcı yok" in text

    async def empty(config, data):
        return {"ok": True, "saglayici": "x", "dosyalar": []}

    monkeypatch.setattr(image_chat, "create_image", empty)
    ok, text = await run_image_command(make_config(), ImageCommand(prompt="kedi"))
    assert ok is False and "döndürmedi" in text


async def test_oturum_gorsel_komutunu_modele_gondermeden_sohbete_yazar(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from fusion_cli.appserver import session as session_module
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.cli import session as cli_session

    model = AsyncMock(side_effect=AssertionError("/görsel modeli çağırmamalı"))
    monkeypatch.setattr(cli_session, "run_agent_task", model)
    calls = []

    async def fake_create(config, data):
        calls.append(data)
        dosya = tmp_path / "g.png"
        return {
            "ok": True,
            "saglayici": "Test",
            "dosyalar": [{"yol": str(dosya), "genislik": 512, "yukseklik": 512}],
        }

    monkeypatch.setattr(image_chat, "create_image", fake_create)
    assert session_module.run_image_command is image_chat.run_image_command
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        sonuc = await app._dispatch(
            Request("g1", "tur.calistir", {"gorev": "/görsel mavi kuş", "gonderim_id": "img-1"})
        )
        assert sonuc["ok"] is True and sonuc["gorsel_komutu"] is True
        assert "g.png" in sonuc["metin"] and calls == [{"istem": "mavi kuş", "oran": "1:1"}]
        assert [m.role for m in app._state.history] == ["user", "assistant"]
        assert app._state.history[0].content == "/görsel mavi kuş"
        model.assert_not_called()
        bos = await app._dispatch(
            Request("g2", "tur.calistir", {"gorev": "/görsel", "gonderim_id": "img-2"})
        )
        assert bos["ok"] is False and "Kullanım" in bos["metin"]
    finally:
        await app.close()


async def test_birden_cok_secim_ayni_turda_birlikte_baglama_girer(tmp_path):
    from fusion_cli.appserver.session import AppSession

    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        app._known_capability = lambda kind, name: True  # type: ignore[method-assign]
        assert app._select_capability({"tur": "mcp", "ad": "github"})["ok"]
        assert app._select_capability({"tur": "mcp", "ad": "notion"})["ok"]
        assert app._select_capability({"tur": "mcp", "ad": "github"})["ok"]  # tekrar eklenmez
        context = app._take_capability_context()
        assert "'github'" in context and "'notion'" in context and context.count("'github'") == 1
        assert app._take_capability_context() == ""  # yalnız bir tur için geçerli
    finally:
        await app.close()
