"""JSONL kaydından olayın geri kurulması.

Tekrar oynatmanın anlamı, kaydedilen turun AYNISINI yeniden üretebilmektir. Araç
çağrısı taşıyan bir model sonucu geri kurulurken çağrılar düşerse kayıt, araç
kullanan hiçbir görevi yeniden üretemez — ve bu sessizce olur: olay geri gelir,
yalnız içi boşalmıştır.
"""

from __future__ import annotations

import io
import json

from fusion_cli.core.events import Event, ModelCallFinished
from fusion_cli.core.types import ModelResult, TokenUsage, ToolCall
from fusion_cli.observability.json_sink import JsonRenderer
from fusion_cli.observability.replay import event_from_payload


def _kaydet(event: Event) -> dict[str, object]:
    """Olayı gerçek JSONL yoluyla yazıp geri okur: testin girdisi de kayıttır."""
    akis = io.StringIO()
    JsonRenderer(akis).handle(event)
    return json.loads(akis.getvalue())


def _model_call_finished(*calls: ToolCall, usage: TokenUsage | None = None) -> ModelCallFinished:
    return ModelCallFinished(
        role="agent",
        result=ModelResult(
            name="agent",
            model="nvidia_nim/test",
            text="",
            latency_ms=12,
            ok=True,
            usage=usage or TokenUsage(),
            tool_calls=calls,
        ),
    )


def test_model_sonucundaki_arac_cagrilari_kayittan_geri_kurulur() -> None:
    cagri = ToolCall(id="call_1", name="read_file", arguments='{"path": "a.py"}')
    payload = _kaydet(_model_call_finished(cagri))

    geri = event_from_payload(payload)

    assert isinstance(geri, ModelCallFinished)
    assert isinstance(geri.result, ModelResult)
    assert len(geri.result.tool_calls) == 1
    kurulan = geri.result.tool_calls[0]
    assert isinstance(kurulan, ToolCall)
    assert kurulan.id == "call_1"
    assert kurulan.name == "read_file"
    assert kurulan.arguments == '{"path": "a.py"}'


def test_arac_cagrisi_olmayan_model_sonucu_bos_demet_dondurur() -> None:
    payload = _kaydet(_model_call_finished())

    geri = event_from_payload(payload)

    assert isinstance(geri, ModelCallFinished)
    assert isinstance(geri.result, ModelResult)
    assert geri.result.tool_calls == ()


def test_bozuk_arac_cagrisi_kaydi_olayin_tamamini_dusurmez() -> None:
    """Tolerans korunur: eksik alanlı çağrı atılır, olay yine geri kurulur."""
    payload = _kaydet(_model_call_finished())
    assert isinstance(payload["result"], dict)
    payload["result"]["tool_calls"] = [{"id": "call_1"}, "metin değil sözlük"]

    geri = event_from_payload(payload)

    assert isinstance(geri, ModelCallFinished)
    assert isinstance(geri.result, ModelResult)
    assert geri.result.tool_calls == ()


def test_model_sonucundaki_token_kullanimi_kayittan_geri_kurulur() -> None:
    payload = _kaydet(
        _model_call_finished(
            usage=TokenUsage(prompt_tokens=13, completion_tokens=21, cost_usd=0.34)
        )
    )

    geri = event_from_payload(payload)

    assert isinstance(geri, ModelCallFinished)
    assert isinstance(geri.result, ModelResult)
    assert geri.result.usage == TokenUsage(
        prompt_tokens=13,
        completion_tokens=21,
        cost_usd=0.34,
    )


def test_kanal_enum_olarak_geri_kurulur():
    """`TokenReceived.channel` Channel'a dönmezse tüketici akış metnini kaybeder (C1-21a)."""
    from fusion_cli.core.events import Channel, TokenReceived

    geri = event_from_payload(_kaydet(TokenReceived(channel=Channel.MAIN, text="merhaba")))

    assert isinstance(geri, TokenReceived) and geri.channel is Channel.MAIN


def test_olcum_bayraklari_geri_kurulur():
    """Tekrar oynatılan kullanım 'ölçülmemiş' görünmemeli (C1-21c)."""
    usage = TokenUsage(
        prompt_tokens=3,
        completion_tokens=4,
        cost_usd=0.5,
        prompt_measured=True,
        completion_measured=True,
        cost_known=True,
    )

    geri = event_from_payload(_kaydet(_model_call_finished(usage=usage)))

    assert isinstance(geri, ModelCallFinished)
    assert geri.result.usage == usage


def test_oneri_ciftleri_ic_demete_cevrilir():
    """`FollowupsSuggested.items` (etiket, görev) çiftleri demet kalmalı (C1-21d)."""
    from fusion_cli.core.events import FollowupsSuggested

    geri = event_from_payload(_kaydet(FollowupsSuggested(items=(("Testleri çalıştır", "pytest"),))))

    assert isinstance(geri, FollowupsSuggested)
    assert geri.items == (("Testleri çalıştır", "pytest"),)
