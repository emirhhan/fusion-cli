"""Yetenek sondajı gerçekten çalıştırılır.

Denetlendi (6 Eylül): `engines/capability_probe.py` yazıldı ve test edildi ama
hiçbir yerden çağrılmıyordu — sondaj yapılmıyor, sonuç hiçbir karara girmiyordu.
Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.

Sondaj `fusion doctor --live` altında çalışır: kota harcar, bu yüzden varsayılan
kurulum denetiminde çalıştırılmaz.
"""

from __future__ import annotations

from fusion_cli.cli.doctor import capability_check
from fusion_cli.core.model_capability import ModelCapability, ToolSupport


def test_kanitlanan_yetenek_okunur_bicimde_raporlanir():
    kontrol = capability_check(
        "gemini_web/main",
        ModelCapability(tool_support=ToolSupport.EMULATED, vision=True),
    )

    assert "gemini_web/main" in kontrol.name
    assert "araç" in kontrol.value.casefold()
    assert kontrol.ok is True


def test_araci_kanitlanamayan_model_uyari_verir():
    kontrol = capability_check(
        "zayif/model", ModelCapability(tool_support=ToolSupport.NONE, vision=False)
    )

    assert kontrol.ok is False
    assert kontrol.remedy


def test_bilinmeyen_yetenek_ne_gecti_ne_kaldi():
    """ "Bilmiyoruz" ayrı bir durumdur; başarı da başarısızlık da sayılmaz."""
    kontrol = capability_check("yeni/model", ModelCapability(tool_support=ToolSupport.UNKNOWN))

    assert kontrol.ok is None


async def test_native_probe_uses_actual_structured_result_and_keeps_missing_revision_unknown():
    from fusion_cli.cli.doctor import probe_native_capability
    from fusion_cli.core.types import ModelResult, ToolCall

    from .fakes import FakeProvider, request

    provider = FakeProvider("sample", chunks=("Yanıt",))

    # Provider public complete sınırı kontrollü gerçek proje sonucu döndürür.
    async def complete(_request):
        assert _request.tools
        return ModelResult(
            name="doctor",
            model="requested",
            text="",
            latency_ms=1,
            ok=True,
            tool_calls=(ToolCall(id="actual-call", name="sum", arguments='{"a":2,"b":3}'),),
        )

    provider.complete = complete
    check = await probe_native_capability("requested", provider, request())
    assert check.ok is True
    assert "native" in check.value
    assert check.evidence[0].source == "native-probe"
    assert check.evidence[0].measured_at is not None
    assert check.evidence[0].model_revision is None
