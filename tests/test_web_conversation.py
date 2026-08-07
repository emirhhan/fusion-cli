"""Web sohbet sürekliliği — her turda sıfırdan sohbet açılmaz.

Eskiden her araç turunda `new_chat_url`'e gidilip YENİ bir sohbet açılıyor ve
konuşmanın tamamı tek düz metin bloğu olarak yeniden gönderiliyordu. Model gerçek
bir araç-sonucu protokolü değil "[Önceki araç çağrıları]" başlıklı bir metin
görüyordu; aynı çağrıyı yeniden üretmesi bunun doğal sonucuydu.

Bu dosya sahte bir Playwright yüzeyiyle çalışır: ağ yok, tarayıcı yok.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.types import Message
from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    BrowserSessionPool,
    build_browser_transport,
    conversation_digest,
    format_browser_prompt,
)
from fusion_cli.providers.web_session import WebSessionCredential


class _FakePage:
    """Gönderilen prompt'ları kaydeden sahte sayfa."""

    def __init__(self, log: list[tuple[str, str]]) -> None:
        self._log = log
        self.closed = False
        self.goto_count = 0

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_count += 1
        self._log.append(("goto", url))

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, log: list[tuple[str, str]]) -> None:
        self._log = log
        self.pages_created = 0

    async def new_page(self) -> _FakePage:
        self.pages_created += 1
        return _FakePage(self._log)


@pytest.fixture
def log() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def pool(monkeypatch, log) -> BrowserSessionPool:
    manager = BrowserSessionPool()
    context = _FakeContext(log)

    async def _context_for(session, credential):
        return context

    monkeypatch.setattr(manager, "context_for", _context_for)

    async def _open(page, definition):
        await page.goto(definition.new_chat_url)

    async def _send(page, definition, prompt):
        log.append(("send", prompt))
        return "tamam"

    monkeypatch.setattr(web_browser, "_open_conversation", _open)
    monkeypatch.setattr(web_browser, "_send_turn", _send)
    manager.fake_context = context  # type: ignore[attr-defined]
    return manager


def _session() -> WebSessionConfig:
    return WebSessionConfig(
        model="chatgpt_web/main/auto",
        provider="chatgpt_web",
        account="main",
        transport="browser",
        tool_support="emulated",
    )


def _messages(count: int) -> tuple[Message, ...]:
    return tuple(Message("user", f"mesaj-{index}") for index in range(count))


async def test_ikinci_tur_yeni_sohbet_acmaz(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "chatgpt_web/main/auto")
    await transport(credential, _messages(3), "chatgpt_web/main/auto")

    gotos = [entry for entry in log if entry[0] == "goto"]
    assert len(gotos) == 1, "ikinci tur için yeniden sohbet açılmamalı"
    assert pool.fake_context.pages_created == 1


async def test_ikinci_tur_yalnizca_yeni_mesaji_gonderir(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "m")
    await transport(credential, _messages(3), "m")

    gonderilen = [entry[1] for entry in log if entry[0] == "send"]
    assert "mesaj-0" in gonderilen[0] and "mesaj-1" in gonderilen[0]
    # İkinci turda geçmiş yeniden gönderilmez.
    assert "mesaj-2" in gonderilen[1]
    assert "mesaj-0" not in gonderilen[1]
    assert "mesaj-1" not in gonderilen[1]


async def test_gecmis_degisirse_sohbet_sifirlanir(pool, log):
    """Bağlam sıkıştırıldıysa devam etmek modeli yanlış konuşmada bırakırdı."""
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(3), "m")
    # Geçmiş yeniden yazıldı: önek artık eşleşmiyor.
    degisen = (Message("user", "bambaşka"), *_messages(3))
    await transport(credential, degisen, "m")

    gotos = [entry for entry in log if entry[0] == "goto"]
    assert len(gotos) == 2, "önek değiştiyse sohbet sıfırlanmalı"
    gonderilen = [entry[1] for entry in log if entry[0] == "send"]
    assert "bambaşka" in gonderilen[1]
    assert "mesaj-0" in gonderilen[1], "sıfırlanan sohbete geçmişin tamamı gider"


async def test_ayni_uzunluktaki_liste_devam_sayilmaz(pool, log):
    """Mesaj eklenmediyse gönderilecek yeni bir şey yoktur; sohbet yeniden kurulur."""
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "m")
    await transport(credential, _messages(2), "m")

    assert len([entry for entry in log if entry[0] == "goto"]) == 2


async def test_secici_hatasi_sohbeti_birakir(pool, log, monkeypatch):
    """Sohbet bilinmeyen bir duruma düşerse bırakılır; sonraki tur sıfırdan başlar."""
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()
    await transport(credential, _messages(2), "m")
    assert pool.conversation("chatgpt_web", "main") is not None

    cagri = {"sayi": 0}

    async def _patlayan(page, definition, prompt):
        cagri["sayi"] += 1
        raise web_browser.WebBrowserSelectorError("arayüz değişti")

    monkeypatch.setattr(web_browser, "_send_turn", _patlayan)

    with pytest.raises(web_browser.WebBrowserSelectorError):
        await transport(credential, _messages(3), "m")

    assert pool.conversation("chatgpt_web", "main") is None
    assert cagri["sayi"] == 2, "aynı profilde tam olarak bir kez yeniden denenir"


def test_devam_promptu_gecmis_basliklarini_tasimaz():
    yeni = format_browser_prompt(
        (Message("tool", "çıktı", name="run_shell", ok=True),), continuation=True
    )
    assert "ARAÇ SONUCU (run_shell, başarılı)" in yeni
    assert "### TALİMAT" in yeni


def test_ozet_rol_ve_icerigi_birlikte_kapsar():
    a = (Message("user", "x"),)
    b = (Message("assistant", "x"),)
    assert conversation_digest(a) != conversation_digest(b)
    assert conversation_digest(a) == conversation_digest((Message("user", "x"),))


# --- Teşhis izi ---------------------------------------------------------------- #
#
# Web modeli araç sonuçlarına tepki vermediğinde ekranda yalnızca araç çağrıları
# görünür; modelin metni taklit araç ayrıştırmasında tüketilir. "Ne gördü, ne
# cevapladı" sorusu başka türlü cevaplanamaz.


async def test_iz_acikken_gonderilen_ve_gelen_kaydedilir(pool, log, tmp_path):
    transport = build_browser_transport(_session(), pool=pool, trace_dir=tmp_path)

    await transport(WebSessionCredential(), _messages(2), "m")

    (dosya,) = list(tmp_path.glob("*.jsonl"))
    kayit = json.loads(dosya.read_text(encoding="utf-8").strip())
    assert "mesaj-0" in kayit["gonderilen"]
    assert kayit["gelen"] == "tamam"
    assert kayit["devam"] is False


async def test_iz_kapaliyken_hicbir_sey_yazilmaz(pool, log, tmp_path):
    transport = build_browser_transport(_session(), pool=pool, trace_dir=None)

    await transport(WebSessionCredential(), _messages(2), "m")

    assert list(tmp_path.iterdir()) == []


async def test_devam_turu_iz_kaydinda_isaretlenir(pool, log, tmp_path):
    transport = build_browser_transport(_session(), pool=pool, trace_dir=tmp_path)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "m")
    await transport(credential, _messages(3), "m")

    (dosya,) = list(tmp_path.glob("*.jsonl"))
    kayitlar = [json.loads(satir) for satir in dosya.read_text(encoding="utf-8").splitlines()]
    assert [kayit["devam"] for kayit in kayitlar] == [False, True]
    # Devam turunda YALNIZCA yeni mesaj gönderilmiş olmalı.
    assert "mesaj-0" not in kayitlar[1]["gonderilen"]
