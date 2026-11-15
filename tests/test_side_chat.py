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


async def test_arka_plan_talk_web_oturumunu_es_gecer(monkeypatch) -> None:
    from fusion_cli.appserver.side_chat import _default_provider
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.providers import factory

    config = SimpleNamespace(
        agent=ModelSpec(
            "talk",
            "chatgpt_web/main/auto",
            fallback=("gemini_web/main/auto", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"),
        ),
        runtime=SimpleNamespace(retry_delays_s=(1.0,)),
    )
    selected = {}

    def build(spec, **kwargs):
        selected.update(model=spec.model, fallback=spec.fallback, **kwargs)
        return _Provider()

    monkeypatch.setattr(factory, "build_provider", build)
    monkeypatch.setattr("fusion_cli.config.model_lookup.configured_model_specs", lambda _: ())
    assert _default_provider(config, browserless=True) is not None
    assert selected["model"].startswith("nvidia_nim/")
    assert selected["fallback"] == ()
    assert selected["web_sessions"] is None

    config.agent = ModelSpec("talk", "chatgpt_web/main/auto")
    assert _default_provider(config, browserless=True) is None


async def test_talk_arastirmasi_http_kaynaklarini_aracsiz_modele_verir(
    monkeypatch, tmp_path
) -> None:
    from fusion_cli.appserver import voice_research
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.core.types import ModelSpec

    provider = _Provider("2026'da yeni nesil Andromeda duyuruldu.")
    config = SimpleNamespace(
        agent=ModelSpec("talk", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")
    )
    monkeypatch.setattr(
        voice_research,
        "_default_provider",
        lambda _, *, browserless: provider if browserless else None,
    )
    url = "https://example.com/announcement"
    monkeypatch.setattr(voice_research, "web_search", lambda *_: ToolResult(f"• Duyuru\n  {url}"))
    monkeypatch.setattr(
        voice_research, "web_fetch", lambda *_: ToolResult("2026 duyurusunun metni")
    )

    result = await voice_research.research_voice(
        config, tmp_path, {"soru": "2026 güncellemeleri neler?"}
    )
    assert result["ok"] is True
    assert result["kaynaklar"] == [url]
    request = provider.requests[0]
    assert request.tools == ()
    assert "2026 duyurusunun metni" in request.messages[-1].content


async def test_talk_arastirmasi_alan_adini_dogrudan_dener_ve_guveni_belirsiz_birakir(
    monkeypatch, tmp_path
) -> None:
    from fusion_cli.appserver import voice_research
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.core.types import ModelSpec

    provider = _Provider("Sitenin kendi iade koşulları var.")
    config = SimpleNamespace(
        agent=ModelSpec("talk", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")
    )
    monkeypatch.setattr(voice_research, "_default_provider", lambda _, **__: provider)
    queries, fetched = [], []

    def search(args, _):
        queries.append(args["query"])
        return ToolResult.failure("Arama yok.")

    def fetch(args, _):
        fetched.append(args["url"])
        return ToolResult("Hakkımızda ve iade koşulları.")

    monkeypatch.setattr(voice_research, "web_search", search)
    monkeypatch.setattr(voice_research, "web_fetch", fetch)
    result = await voice_research.research_voice(
        config, tmp_path, {"soru": "Örnek nokta kom güvenilir mi?", "ayrintili": True}
    )

    assert fetched == ["https://örnek.com"]
    assert len(queries) > 1
    assert result["metin"].startswith("Bağımsız kaynaklardan güvenilirliğini doğrulayamadım.")
    assert '"istenen_alan_adi": "örnek.com"' in provider.requests[0].messages[-1].content


async def test_talk_ticari_unvan_icin_sitede_isletmeci_kaniti_ister(monkeypatch, tmp_path) -> None:
    from fusion_cli.appserver import voice_research
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.core.types import ModelSpec

    provider = _Provider('{"unvan": "Örnek Ticaret A.Ş.", "kaynak": 0}')
    config = SimpleNamespace(
        agent=ModelSpec("talk", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")
    )
    monkeypatch.setattr(voice_research, "_default_provider", lambda _, **__: provider)
    monkeypatch.setattr(voice_research, "web_search", lambda *_: ToolResult.failure("Arama yok."))
    page = "Ödeme aracısı: Örnek Ticaret A.Ş."
    monkeypatch.setattr(voice_research, "web_fetch", lambda *_: ToolResult(page))

    query = {"soru": "ornek.com kime ait, güvenilir mi?"}
    result = await voice_research.research_voice(config, tmp_path, query)
    assert "Örnek Ticaret" not in result["metin"]
    assert "resmi unvanını" in result["metin"]

    page = "İşletmeci: Örnek Ticaret A.Ş."
    result = await voice_research.research_voice(config, tmp_path, query)
    assert "Örnek Ticaret A.Ş." in result["metin"]
