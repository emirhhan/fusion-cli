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


def _model_call_finished(*calls: ToolCall) -> ModelCallFinished:
    return ModelCallFinished(
        role="agent",
        result=ModelResult(
            name="agent",
            model="nvidia_nim/test",
            text="",
            latency_ms=12,
            ok=True,
            usage=TokenUsage(),
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
