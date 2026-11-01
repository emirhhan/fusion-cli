"""#444: masaüstü yan sohbeti ana geçmişi okur, değiştirmez; araçsız tek çağrı."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.appserver.side_chat import ask_side, build_messages
from fusion_cli.core.types import Message, ModelResult

pytestmark = pytest.mark.asyncio
_CONFIG = SimpleNamespace(
    runtime=SimpleNamespace(temperature=0.2, max_tokens=512, request_timeout_s=30, max_retries=0)
)


class _Provider:
    def __init__(self, text: str = "kısa yanıt", ok: bool = True) -> None:
        self.requests = []
        self.text, self.ok = text, ok

    async def complete(self, request):
        self.requests.append(request)
        return ModelResult(
            name="p",
            model="m",
            text=self.text,
            latency_ms=1,
            ok=self.ok,
            error=None if self.ok else "kota",
        )


async def test_yan_soru_ana_baglami_okur_gecmisi_degistirmez() -> None:
    history = [
        Message("system", "gizli sistem"),
        Message("user", "Siteyi yap"),
        Message("assistant", "index.html yazıldı"),
        Message("tool", "araç çıktısı"),
    ]
    before = list(history)
    provider = _Provider()
    side = [{"rol": "kullanici", "metin": "önceki"}, {"rol": "asistan", "metin": "cevap"}]
    result = await ask_side(
        _CONFIG,
        history,
        {"soru": "Bu neden?", "gecmis": side},
        provider_factory=lambda _c: provider,
    )
    assert result == {"ok": True, "metin": "kısa yanıt"}
    assert history == before
    request = provider.requests[0]
    assert request.tools == ()
    system = request.messages[0].content
    assert (
        "index.html yazıldı" in system
        and "gizli sistem" not in system
        and "araç çıktısı" not in system
    )
    assert [m.role for m in request.messages[1:]] == ["user", "assistant", "user"]
    assert request.messages[-1].content == "Bu neden?"


async def test_bos_soru_ve_model_hatasi() -> None:
    assert not (
        await ask_side(_CONFIG, [], {"soru": " "}, provider_factory=lambda _c: _Provider())
    )["ok"]
    failed = await ask_side(
        _CONFIG, [], {"soru": "x"}, provider_factory=lambda _c: _Provider(ok=False)
    )
    assert failed == {"ok": False, "metin": "kota"}


async def test_bozuk_yan_gecmis_yok_sayilir() -> None:
    messages = build_messages(
        [], [{"rol": "sistem", "metin": "x"}, "bozuk", {"rol": "asistan"}], "s"
    )
    assert [m.role for m in messages] == ["system", "user"]
