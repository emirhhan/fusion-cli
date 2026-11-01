"""Olay ve soru köprüleri."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from fusion_cli.appserver.bridges import PendingQuestions, ProtocolPrompter, ProtocolSink
from fusion_cli.core.events import Event, TurnOutcome
from fusion_cli.core.tools import AuthorizationScope, Tool, ToolEffect
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalRequest


@dataclass(frozen=True, slots=True)
class _SerilestirilemeyenOlay(Event):
    """Testte bilinçli olarak JSON'a çevrilemeyen bir alan taşır (sınıf nesnesi)."""

    deger: type = int


class _Tool:
    name = "write_file"


def _request(danger: str | None = None, args: dict[str, object] | None = None) -> ApprovalRequest:
    return ApprovalRequest(tool=_Tool(), args=args or {"path": "a.txt"}, danger=danger)


def test_olay_satir_olarak_yazilir() -> None:
    satirlar: list[str] = []

    ProtocolSink(satirlar.append).handle(TurnOutcome(status="completed", elapsed_s=1.0))

    yuk = json.loads(satirlar[0])
    assert yuk["tip"] == "olay"
    assert yuk["veri"]["olay"] == "TurnOutcome"
    assert yuk["veri"]["status"] == "completed"


async def test_onay_sorusu_cevapla_eslesir() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)

    soru = json.loads(satirlar[0])
    assert soru["tip"] == "soru"
    assert soru["veri"]["tur"] == "onay"
    assert pending.resolve(soru["id"], {"secim": "once"}) is True

    assert await gorev is ApprovalAnswer.ONCE


async def test_yikici_istekte_oturum_secenegi_gonderilmez() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request(danger="dosya siler")))
    await asyncio.sleep(0)

    secenekler = json.loads(satirlar[0])["veri"]["secenekler"]
    assert "session" not in [seçenek["deger"] for seçenek in secenekler]

    pending.resolve(json.loads(satirlar[0])["id"], {"secim": "deny"})
    await gorev


async def test_remote_session_option_explains_exact_authorization_scope() -> None:
    """Oturum izni seçilmeden sunucu, hesap, eylem ve hedef görülebilir."""
    lines: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(lines.append, pending)
    request = ApprovalRequest(
        tool=_Tool(),
        args={"path": "document-42"},
        danger=None,
        effect=ToolEffect.REMOTE_WRITE,
        authorization_scope=AuthorizationScope(
            "documents", "work-account", "update", ("document-42", "document-7")
        ),
    )
    task = asyncio.create_task(prompter.confirm(request))
    await asyncio.sleep(0)
    try:
        payload = json.loads(lines[0])
        option = next(item for item in payload["veri"]["secenekler"] if item["deger"] == "session")
        assert all(
            value in option.get("aciklama", "")
            for value in ("documents", "work-account", "update", "document-42", "document-7")
        )
    finally:
        pending.cancel_all()
        await task


async def test_soru_serbest_metin_doner() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.ask("hangi dil?"))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[0])["id"], {"metin": "python"})

    assert await gorev == "python"


async def test_cevapsiz_kapanista_onay_reddedilir() -> None:
    """Uygulama cevap vermeden kapanırsa tur güvenli biçimde bitmeli."""
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.cancel_all()

    assert await gorev is ApprovalAnswer.DENY


def test_eslesmeyen_kimlik_yok_sayilir() -> None:
    assert PendingQuestions().resolve("olmayan", {"secim": "once"}) is False


async def test_question_transport_failure_releases_pending_owner() -> None:
    """Gönderilemeyen soru askıda kalmaz; hata çağırana ulaşır."""
    pending = PendingQuestions()
    closed: list[str] = []

    def broken_writer(line: str) -> None:
        raise BrokenPipeError("bağlantı kapalı")

    prompter = ProtocolPrompter(broken_writer, pending, on_closed=closed.append)
    with pytest.raises(BrokenPipeError):
        await prompter.ask("Hangi hedef?")
    assert len(closed) == 1
    assert pending.resolve(closed[0], {"metin": "geç cevap"}) is False
    assert pending.cancel_all() == ()


async def test_restarted_question_owner_rejects_previous_process_answer() -> None:
    """Aynı görev kimliği yeniden açılsa bile eski cevap yeni soruya izin vermez."""
    previous = PendingQuestions()
    old_id, _ = previous.new_question("same-attempt")
    previous.cancel_all()
    current = PendingQuestions()
    new_id, new_answer = current.new_question("same-attempt")
    try:
        assert old_id != new_id
        assert not current.answer(old_id, {"decisionId": "old-decision", "secim": "once"})
        assert not new_answer.done()
        assert current.answer(new_id, {"decisionId": "new-decision", "secim": "deny"})
        assert (await new_answer)["secim"] == "deny"
    finally:
        current.cancel_all()


def test_serilestirilemeyen_olay_sessizce_kaybolmaz() -> None:
    """I6: `_plain`in fırlattığı `TypeError` yutulmaz, `ProtocolError` olayına döner."""
    satirlar: list[str] = []

    ProtocolSink(satirlar.append).handle(_SerilestirilemeyenOlay())

    assert len(satirlar) == 1
    yuk = json.loads(satirlar[0])
    assert yuk["tip"] == "olay"
    assert yuk["veri"]["olay"] == "ProtocolError"
    assert "_SerilestirilemeyenOlay" in yuk["veri"]["mesaj"]


async def test_onay_yukunde_arguman_degeri_de_tasinir() -> None:
    """Onay teli, hangi komutun/dosyanın onaylandığını görsün diye argüman
    DEĞERLERİNİ de taşımalı — yalnız adları göstermek kullanıcıyı körlemesine
    onaya zorlardı ve zaten `ToolExecuted.args` olayıyla aynı değerler tele
    akıyordu (redaksiyon anlamsızdı)."""
    deger = "rm -rf gizli-klasor"
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(
        prompter.confirm(_request(args={"zeta": deger, "alpha": "sabit"}))
    )
    await asyncio.sleep(0)

    yuk = json.loads(satirlar[0])
    assert yuk["veri"]["argumanlar"] == ["alpha='sabit'", f"zeta={deger!r}"]
    assert deger in satirlar[0]

    pending.resolve(yuk["id"], {"secim": "deny"})
    await gorev


async def test_iptal_edilen_onay_bekleyen_soruyu_temizler() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    soru_kimligi = json.loads(satirlar[0])["id"]

    gorev.cancel()
    with pytest.raises(asyncio.CancelledError):
        await gorev

    assert soru_kimligi not in pending._pending
    assert pending.resolve(soru_kimligi, {"secim": "once"}) is False


async def test_answer_receipt_retry_does_not_resolve_twice() -> None:
    """Kaybolan makbuzun tekrarı aynı kararı kabul eder; farklı yanıtı reddeder."""
    pending = PendingQuestions()
    identifier, future = pending.new_question()
    answer = {"secim": "once", "decisionId": "offline-decision"}
    assert pending.answer(identifier, answer)
    assert pending.answer(identifier, answer)
    assert not pending.answer(identifier, {"secim": "deny", "decisionId": "offline-decision"})
    assert await future == answer


async def test_cancelled_question_cannot_be_authorized_by_late_reply() -> None:
    pending = PendingQuestions()
    identifier, future = pending.new_question()
    pending.cancel_all()
    assert not pending.answer(identifier, {"secim": "once", "decisionId": "late"})
    assert await future == {}


async def test_cancel_returns_exact_closed_question_ids() -> None:
    pending = PendingQuestions()
    first, _ = pending.new_question()
    second, _ = pending.new_question()
    assert pending.cancel_all() == (first, second)
    assert pending.cancel_all() == ()


async def test_earlier_answer_receipt_is_replayable_after_another_question() -> None:
    """İki açık sorunun makbuzları ağda farklı sırayla tekrar gelebilir."""
    pending = PendingQuestions()
    first, first_result = pending.new_question("same-turn")
    second, second_result = pending.new_question("same-turn")
    one = {"secim": "once", "decisionId": "first-decision"}
    two = {"secim": "deny", "decisionId": "second-decision"}
    assert pending.answer(first, one)
    assert pending.answer(second, two)
    assert pending.answer(first, one)
    assert not pending.answer(first, {**one, "secim": "session"})
    assert await first_result == one
    assert await second_result == two


async def test_answer_receipt_history_is_bounded_and_cleared_on_stop() -> None:
    """Pencere dışında kalan ACK yeni izin oluşturmaz; durdurma tümünü siler."""
    pending = PendingQuestions(receipt_history_limit=2)
    identifiers = []
    for index in range(3):
        identifier, future = pending.new_question("turn")
        answer = {"secim": "once", "decisionId": str(index)}
        assert pending.answer(identifier, answer)
        assert await future == answer
        identifiers.append((identifier, answer))
    assert not pending.answer(*identifiers[0])
    assert pending.answer(*identifiers[-1])
    pending.cancel_all()
    assert not pending.answer(*identifiers[-1])


def test_dairesel_yapi_valueerror_olay_kaybolmaz(monkeypatch) -> None:
    """Ölçüldü (30 Ekim, S1-10): `encode_event` `ValueError` (dairesel yapı) fırlatınca
    yalnız `TypeError` yakalandığından olay `EventBus.failures`'a gömülüp kayboluyordu."""
    from fusion_cli.appserver import bridges

    def bozuk(_payload: dict) -> str:
        raise ValueError("Circular reference detected")

    monkeypatch.setattr(bridges, "encode_event", bozuk)
    satirlar: list[str] = []

    ProtocolSink(satirlar.append).handle(TurnOutcome(status="completed", elapsed_s=1.0))

    yuk = json.loads(satirlar[0])
    assert yuk["veri"]["olay"] == "ProtocolError"


async def test_onay_argumani_uzunluk_sinirli_ve_maskelidir() -> None:
    """Ölçüldü (30 Ekim, S1-12): 2 MB `content` olduğu gibi kartın telinde taşınıyordu."""
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(
        prompter.confirm(
            _request(args={"content": "a" * 100_000, "env": "Bearer abcdef1234567890xyz"})
        )
    )
    await asyncio.sleep(0)

    yuk = json.loads(satirlar[0])
    assert len(satirlar[0]) < 10_000
    assert any("karakter daha" in arguman for arguman in yuk["veri"]["argumanlar"])
    assert "abcdef1234567890xyz" not in satirlar[0]

    pending.resolve(yuk["id"], {"secim": "deny"})
    await gorev


# S1-11 — Ölçüldü (30 Ekim): cevapsız onay `await future` ile SONSUZA dek bekliyordu;
# uygulama açık ama kullanıcı yokken tur (ve turu tutan kilit) hiç bitmiyordu.
async def test_cevapsiz_onay_zaman_asiminda_reddedilir_ve_olay_yayilir() -> None:
    satirlar: list[str] = []
    kapananlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(
        satirlar.append, pending, on_closed=kapananlar.append, approval_timeout_s=0.05
    )

    cevap = await prompter.confirm(_request())

    assert cevap is ApprovalAnswer.DENY
    soru_id = json.loads(satirlar[0])["id"]
    assert kapananlar == [soru_id]
    olay = json.loads(satirlar[-1])
    assert olay["tip"] == "olay"
    assert olay["veri"]["olay"] == "OnayZamanAsimi"
    assert olay["veri"]["id"] == soru_id
    assert olay["veri"]["arac"] == "write_file"
    # Geç gelen cevap artık hiçbir soruyla eşleşmez; araç ikinci kez sorulmaz.
    assert pending.resolve(soru_id, {"secim": "once"}) is False


async def test_zaman_asimi_serbest_metin_sorusuna_uygulanmaz() -> None:
    """Zaman aşımı yalnız ONAY içindir; kullanıcıya açık uçlu soru süreyle reddedilmez."""
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending, approval_timeout_s=0.05)

    gorev = asyncio.ensure_future(prompter.ask("hangi dil?"))
    await asyncio.sleep(0.15)
    assert not gorev.done()
    pending.resolve(json.loads(satirlar[0])["id"], {"metin": "python"})

    assert await gorev == "python"


async def test_zamaninda_gelen_onay_zaman_asimina_takilmaz() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending, approval_timeout_s=5.0)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[0])["id"], {"secim": "once"})

    assert await gorev is ApprovalAnswer.ONCE
    assert all(json.loads(s)["veri"].get("olay") != "OnayZamanAsimi" for s in satirlar)


async def test_onay_yukunde_isteyen_alt_ajan_tasinir() -> None:
    """P-034: kart "Alt ajan X izin istiyor" diyebilsin; ana ajanda alan None."""
    import dataclasses

    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(
        prompter.confirm(dataclasses.replace(_request(), agent_label="Denetçi (denetci-1)"))
    )
    await asyncio.sleep(0)
    soru = json.loads(satirlar[0])
    assert soru["veri"]["ajan"] == "Denetçi (denetci-1)"
    pending.resolve(soru["id"], {"secim": "deny"})
    await gorev

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    assert json.loads(satirlar[1])["veri"]["ajan"] is None
    pending.resolve(json.loads(satirlar[1])["id"], {"secim": "deny"})
    await gorev


async def test_kalici_izin_secenegi_yalniz_kalicilastirilabilen_istekte_sunulur() -> None:
    """P-003: "bir daha sorma" seçeneği yazılacak kuralı açıklar; yıkıcı istekte yoktur."""
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    kabuk = ApprovalRequest(
        tool=Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None),
        args={"command": "git status && npm test --watch"},
        danger=None,
    )
    gorev = asyncio.ensure_future(prompter.confirm(kabuk))
    await asyncio.sleep(0)
    soru = json.loads(satirlar[0])
    always = next(s for s in soru["veri"]["secenekler"] if s["deger"] == "always")
    # Claude (#68): zincirde yalnız onay gereken alt komut için kural yazılır.
    assert "Bash(npm test *)" in always["aciklama"]
    assert "git status" not in always["aciklama"]
    assert soru["veri"]["not_alinir"] is True
    pending.resolve(soru["id"], {"secim": "always"})
    assert await gorev is ApprovalAnswer.ALWAYS

    gorev = asyncio.ensure_future(prompter.confirm(_request(danger="dosya siler")))
    await asyncio.sleep(0)
    soru = json.loads(satirlar[-1])
    assert "always" not in [s["deger"] for s in soru["veri"]["secenekler"]]
    pending.resolve(soru["id"], {"secim": "always"})
    # Yıkıcı istekte "always" cevabı bile kalıcı izne dönüşmez: red sayılır.
    assert await gorev is ApprovalAnswer.DENY


def test_dosya_duzenleme_onayi_kalici_kurala_donusmez() -> None:
    """Claude (#68): dosya düzenleme onayı yalnız oturum sonuna dek geçerlidir."""
    assert _request(args={"path": "src/a.py"}).can_persist is False


async def test_ret_notu_kararla_birlikte_tasinir_ve_kirpilir() -> None:
    """P-013: `not` alanı `ApprovalReply` olarak döner; uzun not kesilir, boş not enum bırakır."""
    from fusion_cli.appserver.bridges import APPROVAL_NOTE_MAX_CHARS
    from fusion_cli.engines.agent.approval import ApprovalReply

    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[0])["id"], {"secim": "deny", "not": "  önce testleri yaz "})
    assert await gorev == ApprovalReply(ApprovalAnswer.DENY, "önce testleri yaz")

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[-1])["id"], {"secim": "once", "not": "x" * 5_000})
    cevap = await gorev
    assert isinstance(cevap, ApprovalReply) and len(cevap.note) == APPROVAL_NOTE_MAX_CHARS

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[-1])["id"], {"secim": "once", "not": "   "})
    assert await gorev is ApprovalAnswer.ONCE
