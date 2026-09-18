"""Seçili model HİÇ cevap veremiyorsa yedeğe geçilir.

Ölçüldü (17 Eylül denetimi): kullanıcının seçtiği web oturumu Cloudflare
doğrulamasına takıldı ve 7 turun 7'si düştü. Aynı makinede çalışan, girişi
yapılmış ikinci bir web oturumu vardı ama model "strict" işaretli olduğu için
zincir hiç kurulmadı ve Fusion ona geçmedi.

Ayrım önemlidir: `strict` "kalite için başka modele kayma" demektir. Model
kullanılamıyorsa (oturum yok, captcha, kota) kaymak kaliteyi düşürmez;
alternatifi hiç cevap alamamaktır.
"""

from __future__ import annotations

from fusion_cli.core.types import is_unavailable_error


def test_captcha_kullanilamaz_sayilir() -> None:
    assert is_unavailable_error(
        "web oturumu hatası: authentication: ChatGPT Web (Plus/Pro) insan doğrulaması "
        "(captcha) istiyor."
    )


def test_oturum_kapali_kullanilamaz_sayilir() -> None:
    assert is_unavailable_error("authentication: Gemini oturumu açık değil veya süresi dolmuş.")


def test_kota_kullanilamaz_sayilir() -> None:
    assert is_unavailable_error("rate limit exceeded")


def test_normal_model_hatasi_kullanilamaz_sayilmaz() -> None:
    """Modelin kötü cevabı yedeğe geçiş sebebi DEĞİLDİR."""
    assert not is_unavailable_error("model boş yanıt verdi")
    assert not is_unavailable_error(None)


async def test_strict_kipte_kullanilamaz_modelden_yedege_gecilir() -> None:
    from fusion_cli.core.types import CompletionRequest, Message, ModelResult, ModelSpec
    from fusion_cli.providers.chain import FallbackProvider

    class _Sahte:
        def __init__(self, label: str, sonuc: ModelResult) -> None:
            self.label = label
            self._sonuc = sonuc

        async def complete(self, _request: CompletionRequest) -> ModelResult:
            return self._sonuc

    kullanilamaz = ModelResult(
        name="agent", model="chatgpt_web", text="", latency_ms=0, ok=False,
        error="authentication: captcha"
    )
    calisan = ModelResult(name="agent", model="gemini_web", text="oldu", latency_ms=1, ok=True)

    zincir = FallbackProvider(
        [_Sahte("chatgpt_web", kullanilamaz), _Sahte("gemini_web", calisan)],
        role="agent",
        only_when_unavailable=True,
    )

    sonuc = await zincir.complete(
        CompletionRequest(
            messages=(Message("user", "merhaba"),), temperature=0.0, max_tokens=64, timeout_s=5.0
        )
    )

    assert sonuc.model == "gemini_web"
    assert ModelSpec  # import kullanıldı


async def test_strict_kipte_kalite_hatasinda_yedege_gecilmez() -> None:
    """Model cevap verebiliyorsa ama cevabı kötüyse strict seçim korunur."""
    from fusion_cli.core.types import CompletionRequest, Message, ModelResult
    from fusion_cli.providers.chain import FallbackProvider

    class _Sahte:
        def __init__(self, label: str, sonuc: ModelResult) -> None:
            self.label = label
            self._sonuc = sonuc
            self.cagrildi = False

        async def complete(self, _request: CompletionRequest) -> ModelResult:
            self.cagrildi = True
            return self._sonuc

    zayif = ModelResult(
        name="agent", model="secilen", text="", latency_ms=0, ok=False, error="boş yanıt"
    )
    yedek = _Sahte(
        "yedek", ModelResult(name="agent", model="yedek", text="oldu", latency_ms=1, ok=True)
    )

    zincir = FallbackProvider(
        [_Sahte("secilen", zayif), yedek], role="agent", only_when_unavailable=True
    )
    sonuc = await zincir.complete(CompletionRequest(
            messages=(Message("user", "merhaba"),), temperature=0.0, max_tokens=64, timeout_s=5.0
        ))

    assert yedek.cagrildi is False
    assert sonuc.ok is False
