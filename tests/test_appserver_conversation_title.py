"""Sohbet başlığı sezgiseli — ilk mesajdan kısa ve anlamlı başlık."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver.conversation_title import TITLE_MAX_CHARS, conversation_title
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.transcript_store import TranscriptStore


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("merhaba, bana bir tarayıcı oyunu yaz lütfen", "Tarayıcı oyunu yaz"),
        (
            "Selam! Login sayfasındaki hatayı düzeltir misin?",
            "Login sayfasındaki hatayı düzeltir misin",
        ),
        ("iyi akşamlar kolay gelsin. README dosyasını güncelle", "README dosyasını güncelle"),
        ("hocam şu testleri çalıştır", "Testleri çalıştır"),
    ],
)
def test_conversation_title_drops_greetings_and_filler(message: str, expected: str) -> None:
    assert conversation_title(message) == expected


def test_conversation_title_keeps_meaningful_leading_adjective() -> None:
    # "iyi" tek başına selamlama değildir; yalnız "iyi akşamlar" gibi kalıplar atılır.
    assert conversation_title("iyi bir README yaz") == "İyi bir README yaz"


def test_conversation_title_takes_first_meaningful_sentence() -> None:
    message = "Merhaba. Ödeme sayfası çöküyor. Loglar ekte, bakabilir misin?"
    assert conversation_title(message) == "Ödeme sayfası çöküyor"


def test_conversation_title_capitalizes_turkish_dotted_i() -> None:
    assert conversation_title("istek sayacını ekle") == "İstek sayacını ekle"
    assert conversation_title("ılık su hesabı") == "Ilık su hesabı"


def test_conversation_title_matches_filler_case_insensitively_in_turkish() -> None:
    # "İ" Python'da "i̇" olarak küçülür; katlama Türkçe kurala göre yapılmalı.
    assert conversation_title("İYİ AKŞAMLAR. Grafiği çiz") == "Grafiği çiz"


def test_conversation_title_cuts_long_text_at_word_boundary() -> None:
    message = (
        "kullanıcı kayıt formuna e-posta doğrulaması ekle ve hatalı girişlerde "
        "anlaşılır mesajlar göster"
    )
    title = conversation_title(message)
    assert len(title) <= TITLE_MAX_CHARS
    assert message.startswith(title[0].lower() + title[1:])
    # Kelime ortasında kesilmez ve bağlaçla bitmez.
    assert message[len(title)] == " "
    assert not title.endswith((" ve", " ile", " veya"))


def test_conversation_title_hard_cuts_single_huge_word() -> None:
    assert conversation_title("a" * 200) == "A" + "a" * (TITLE_MAX_CHARS - 1)


def test_conversation_title_keeps_inner_punctuation_and_paths() -> None:
    assert conversation_title("`config.py` içindeki #12 hatasını çöz") == (
        "Config.py içindeki #12 hatasını çöz"
    )


def test_conversation_title_skips_code_blocks_and_shortens_urls() -> None:
    message = "```\nTraceback (most recent call last)\n```\nbu hatayı açıkla"
    assert conversation_title(message) == "Bu hatayı açıkla"
    assert conversation_title("https://example.com/a/b?c=1 sayfasını incele") == (
        "Example.com sayfasını incele"
    )


def test_conversation_title_falls_back_to_greeting_when_nothing_else() -> None:
    # Yalnız selam yazılmışsa boş başlık yerine selamın kendisi kalır.
    assert conversation_title("merhaba!") == "Merhaba"


def test_conversation_title_returns_empty_for_blank_input() -> None:
    assert conversation_title("   \n ") == ""
    assert conversation_title("!!! ???") == ""


def _session(tmp_path: Path) -> tuple[AppSession, list[str]]:
    lines: list[str] = []
    return AppSession(lines.append, root=tmp_path, home=tmp_path / "ev"), lines


@pytest.mark.asyncio
async def test_title_request_returns_heuristic_title(tmp_path: Path) -> None:
    session, lines = _session(tmp_path)

    await session.handle(Request(id="1", name="sohbet.baslik", data={"metin": "selam, oyun yaz"}))

    assert json.loads(lines[-1])["veri"] == {"ok": True, "baslik": "Oyun yaz"}


@pytest.mark.asyncio
async def test_title_request_rejects_missing_text(tmp_path: Path) -> None:
    session, lines = _session(tmp_path)

    await session.handle(Request(id="1", name="sohbet.baslik", data={}))

    assert json.loads(lines[-1])["veri"]["ok"] is False


@pytest.mark.asyncio
async def test_conversation_list_uses_same_title_heuristic(tmp_path: Path) -> None:
    session, lines = _session(tmp_path)
    store = TranscriptStore(session._state.config.memory_dir, tmp_path, conversation_id="a")
    store.record_user("merhaba! ödeme sayfası çöküyor")

    await session.handle(Request(id="1", name="sohbet.listele", data={}))

    assert json.loads(lines[-1])["veri"]["sohbetler"][0]["baslik"] == "Ödeme sayfası çöküyor"
