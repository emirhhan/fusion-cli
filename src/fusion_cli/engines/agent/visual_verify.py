"""Görsel kapı — sayfayı GÖREN bir modele dar sorular sorar.

Neden bu biçim: ölçtük. Aynı görsel, aynı model, üç farklı sorma biçimi:

- Tek soru + kırpılmış bölge → "KALP ÇOK BÜYÜK" (doğru)
- Açık uçlu "hataları listele" + tam sayfa → ya susuyor ya olmayan hatalar uyduruyor
- Dört soru tek çağrıda → hepsine HAYIR; temiz görselde de aynı cevap, ayırt etme yok

Bu yüzden her soru AYRI çağrıdır, her çağrı KIRPILMIŞ bir bölgeye bakar ve cevabın
ikili olması beklenir. Belirsiz cevap "sorun yok" sayılır: gürültülü bir kapı hiç
kapı olmamasından kötüdür.

VARSAYILAN KAPALIDIR. Ücretsiz görme modelleri açık uçlu kullanımda güvenilmez
çıktı verdi ve her soru ayrı çağrı olduğu için maliyetlidir. Geometriyle ÖLÇÜLEBİLEN
hiçbir şey buraya sorulmaz — devasa ikon, taşma, boş bölüm zaten ölçülüyor.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

from ...config.models import Config
from ...core.tools import ToolContext
from ...core.types import CompletionRequest, Message
from ...core.verification import VerificationResult

_logger = logging.getLogger(__name__)

#: Görsel başına tanınan süre. Küçük bir modele küçük bir kırpma sorulur.
VISION_TIMEOUT_S = 60.0
#: İkili cevap için yeterli bütçe; uzun açıklama istemiyoruz.
VISION_MAX_TOKENS = 64


@dataclass(frozen=True, slots=True)
class VisualCheck:
    """Bir bölgeye sorulacak TEK soru ve olumlu cevabın karşılığı olan bulgu."""

    name: str
    #: CSS seçici: bu bölge kırpılıp modele gösterilir.
    selector: str
    question: str
    finding: str


#: Sorular bilinçli olarak DAR ve ikili. Ölçülebilir olan hiçbir şey burada değil.
VISUAL_CHECKS: tuple[VisualCheck, ...] = (
    VisualCheck(
        name="header-hizalama",
        selector="header",
        question=(
            "Bu bir web sitesi header'ının ekran görüntüsü. Menü, arama ve ikonlar "
            "TEK BİR YATAY SATIRDA düzgün hizalanmış mı, yoksa bazıları alt satıra mı "
            "kaymış? Alt satıra kayan varsa EVET, hepsi tek satırdaysa HAYIR yaz. "
            "Sadece EVET ya da HAYIR."
        ),
        finding=(
            "Header'daki öğeler tek satırda hizalanmamış; bazıları alt satıra kaymış. "
            "Menü, arama ve ikonları tek satırda tutacak şekilde düzelt "
            "(flex + gap, daralınca gizlenecek öğeleri belirle)."
        ),
    ),
    VisualCheck(
        name="hero-bosluk",
        selector="section:first-of-type, .hero, #hero",
        question=(
            "Bu bir web sitesi hero (giriş) bölümünün ekran görüntüsü. İçerik ile "
            "bölümün kenarları arasında AŞIRI, garip görünen boş alan var mı? "
            "Aşırı boşluk varsa EVET, boşluk dengeliyse HAYIR yaz. Sadece EVET ya da HAYIR."
        ),
        finding=(
            "Hero bölümünde aşırı boş alan var; içerik ekranın ortasında kaybolmuş "
            "görünüyor. Dikey boşluğu azalt (padding-block: clamp(48px, 6vw, 96px))."
        ),
    ),
    VisualCheck(
        name="okunabilirlik",
        selector="section:first-of-type, .hero, #hero",
        question=(
            "Bu ekran görüntüsündeki metinlerin HEPSİ arka planına göre rahat "
            "okunabiliyor mu? Zemine karışan, soluk kalan metin varsa EVET, hepsi "
            "rahat okunuyorsa HAYIR yaz. Sadece EVET ya da HAYIR."
        ),
        finding=(
            "Bazı metinler zemine karışıyor ve okunmuyor. Metin ile arka plan "
            "arasındaki kontrastı en az 4.5:1 yap."
        ),
    ),
)

#: Modelin olumlu cevabı. Bunun dışındaki her şey "sorun yok" sayılır.
_YES = "evet"


def parse_verdict(text: str) -> bool:
    """Model cevabını ikili karara çevir.

    Belirsiz her cevap "sorun yok"tur. Ölçümde model bazen bozuk yazım ("TAMAK")
    ya da soruyu tekrar eden metin üretti; bunlardan sorun çıkarmak kapıyı
    gürültüye boğardı.
    """
    ilk = (text or "").strip().lower().lstrip("*# ").replace("ı", "i")
    return ilk.startswith(_YES)


def to_finding(check: VisualCheck, region: str) -> str:
    """Olumlu cevabı modele verilecek düzeltme talimatına çevir."""
    return f"[{region}] {check.finding}"


class VisualVerifier:
    """Üretilen sayfayı kırpıp gören bir modele dar sorular sorar."""

    def __init__(self, tool_context: ToolContext, config: Config) -> None:
        self._context = tool_context
        self._config = config

    async def verify(self) -> VerificationResult:
        pages = [
            path
            for path in sorted(self._context.touched)
            if path.suffix.lower() in (".html", ".htm") and path.is_file()
        ]
        if not pages or self._config.vision is None:
            return VerificationResult(ok=True)

        try:
            findings = await self._inspect(pages[0])
        except Exception as exc:
            # Tarayıcı ya da görme modeli erişilemezse tur DÜŞMEZ; bu bir iyileştirmedir.
            _logger.debug("görsel doğrulama atlandı: %s", exc)
            return VerificationResult(ok=True)

        if not findings:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False, summary=f"görsel denetimde {len(findings)} sorun", findings=tuple(findings)
        )

    async def _inspect(self, page_path: Path) -> list[str]:
        from playwright.async_api import async_playwright

        findings: list[str] = []
        async with async_playwright() as driver:
            browser = await driver.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                await page.goto(page_path.as_uri(), wait_until="load")
                for check in VISUAL_CHECKS:
                    element = await page.query_selector(check.selector)
                    if element is None:
                        continue
                    shot = await element.screenshot()
                    if await self._ask(check, shot):
                        findings.append(to_finding(check, check.name))
            finally:
                await browser.close()
        return findings

    async def _ask(self, check: VisualCheck, image: bytes) -> bool:
        from ...providers.factory import build_provider

        spec = self._config.vision
        if spec is None:
            return False
        data_uri = "data:image/png;base64," + base64.b64encode(image).decode()
        provider = build_provider(
            spec,
            publisher=None,
            retry_delays_s=self._config.runtime.retry_delays_s,
            background=True,
        )
        result = await provider.complete(
            CompletionRequest(
                messages=(Message("user", check.question, images=(data_uri,)),),
                temperature=self._config.runtime.judge_temperature,
                max_tokens=VISION_MAX_TOKENS,
                timeout_s=VISION_TIMEOUT_S,
                max_retries=0,
            )
        )
        return parse_verdict(result.text) if result.ok else False
