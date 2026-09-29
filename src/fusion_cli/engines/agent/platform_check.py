"""Dış platforma bağlı istekte işe başlamadan resmi kaynaktan yapılabilirlik kontrolü.

Platform bir API iznine/yeteneğine bağlıysa (ör. Instagram story çıkartmaları API'den
eklenemez) bunu işin sonunda değil başında bilmek gerekir. Bu modül:

1. İstekte adı geçen platformu bulur (ad listesi burada kaçınılmazdır: platformun
   kendisi bir özel addır, etki tespitinden çıkarılamaz).
2. `web_search` aracıyla YALNIZ o platformun resmi geliştirici sitesinde arar ve
   sonuçları çırağa "önce yapılabilirliği söyle" notuyla verir.
3. Arama yapılamazsa bunu gizlemez: kısıtların doğrulanmadığı nota ve cevaba yazılır.
4. Öğretmenin bildirdiği bir kısıt cevapta anılmadıysa tur sonunda cevaba eklenir;
   yapılamayan iş yapılmış gibi görünemez.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.events import PlatformChecked
from ...core.redaction import redact
from ...core.types import Message

if TYPE_CHECKING:
    from ...tools.registry import ToolRegistry
    from .loop import AgentDeps, AgentOutcome


@dataclass(frozen=True, slots=True)
class Platform:
    """Dış platform ve resmi geliştirici dokümanının alan adı."""

    name: str
    docs_domain: str


#: Platform adı kalıpları → resmi geliştirici dokümanı. Alan adları platformların
#: kendi yayımladığı geliştirici siteleridir; arama yalnız bu sitelere daraltılır ki
#: üçüncü taraf blog yazıları "resmi kaynak" yerine geçmesin.
_PLATFORMS: tuple[tuple[str, Platform], ...] = (
    (r"instagram", Platform("Instagram", "developers.facebook.com")),
    (r"whatsapp", Platform("WhatsApp", "developers.facebook.com")),
    (r"facebook|\bmeta\b", Platform("Meta", "developers.facebook.com")),
    (r"google\s+ads|adwords", Platform("Google Ads", "developers.google.com")),
    (r"youtube", Platform("YouTube", "developers.google.com")),
    (r"merchant\s+center", Platform("Google Merchant Center", "developers.google.com")),
    (r"shopify", Platform("Shopify", "shopify.dev")),
    (r"tiktok", Platform("TikTok", "developers.tiktok.com")),
    (r"twitter|\bx\s+api\b", Platform("X", "docs.x.com")),
    (r"linkedin", Platform("LinkedIn", "learn.microsoft.com")),
    (r"pinterest", Platform("Pinterest", "developers.pinterest.com")),
    (r"trendyol", Platform("Trendyol", "developers.trendyol.com")),
    (r"woocommerce", Platform("WooCommerce", "woocommerce.github.io")),
)

#: Bir platform için modele verilen arama sonucu üst sınırı. Web oturumlu modellerin
#: istem bütçesi dar; bu, mevcut öğretmen brief'inin (25k) küçük bir kesridir.
_RESULT_CHARS = 3_000

#: Sorguya eklenen görev kesiti: arama motoruna tüm istemi vermek sonucu bulandırır.
_QUERY_TASK_CHARS = 80


def detect_platforms(task: str) -> tuple[Platform, ...]:
    """İstekte adı geçen dış platformları (tekrarsız, sırasıyla) döndür."""
    found: dict[str, Platform] = {}
    lowered = task.lower()
    for pattern, platform in _PLATFORMS:
        if re.search(pattern, lowered) and platform.name not in found:
            found[platform.name] = platform
    return tuple(found.values())


def _query(platform: Platform, task: str) -> str:
    kesit = " ".join(task.split())[:_QUERY_TASK_CHARS]
    return f"site:{platform.docs_domain} {platform.name} API {kesit}"


async def run_platform_check(
    task: str, messages: list[Message], deps: AgentDeps, registry: ToolRegistry
) -> None:
    """Platform varsa resmi kaynağı ara ve sonucu çırağın bağlamına koy."""
    platforms = detect_platforms(task)
    if not platforms:
        return
    names = tuple(platform.name for platform in platforms)
    sources: list[str] = []
    if registry.get("web_search") is not None:
        for platform in platforms:
            try:
                async with asyncio.timeout(deps.config.runtime.request_timeout_s):
                    result = await registry.execute(
                        "web_search", {"query": _query(platform, task)}, deps.tool_context
                    )
            except TimeoutError:
                continue
            if result.ok and result.output.strip() and "sonuç bulunamadı" not in result.output:
                sources.append(f"[{platform.name} · {platform.docs_domain}]\n"
                               + redact(result.output)[:_RESULT_CHARS])
    deps.platform_check_verified = bool(sources)
    deps.platform_names = names
    if sources:
        note = (
            "FUSION_NOT: İstek dış platforma bağlı ("
            + ", ".join(names)
            + "). Resmi dokümandan bulunan kaynaklar aşağıda. İşe başlamadan bunlara göre "
            "neyin API ile YAPILAMAYACAĞINI kısaca kullanıcıya söyle ve uygulanabilir "
            "alternatifi öner; kaynakta desteklenmeyen işi yapılmış gibi sunma. Gerekirse "
            "`web_fetch` ile sayfayı aç.\n\n" + "\n\n".join(sources)
        )
    else:
        note = (
            "FUSION_NOT: İstek dış platforma bağlı ("
            + ", ".join(names)
            + ") ama resmi dokümana ulaşılamadı. Platformun API kısıtlarını ezberden kesin "
            "bilgi gibi sunma; doğrulanmadığını kullanıcıya açıkça söyle."
        )
    messages.append(Message("user", note, harness_note=True))
    deps.publisher.publish(
        PlatformChecked(
            platforms=names,
            method="resmi-kaynak" if sources else "dogrulanamadi",
            sources=len(sources),
        )
    )


def ensure_limitations_disclosed(outcome: AgentOutcome, deps: AgentDeps) -> None:
    """Bildirilen kısıt cevapta yoksa cevaba ekle; doğrulanamayan platformu belirt."""
    lines: list[str] = []
    text = outcome.final_text.lower()
    for part in deps.platform_limitations:
        if part.topic.lower() not in text:
            lines.append(
                f"- Yapılamayan: {part.topic} — {part.reason}. Alternatif: {part.alternative}."
            )
    unverified = " kısıtları resmi kaynaktan doğrulanamadı."
    if deps.platform_names and not deps.platform_check_verified and unverified not in text:
        lines.append("- " + ", ".join(deps.platform_names) + unverified)
    if lines:
        outcome.final_text = (
            outcome.final_text.rstrip() + "\n\nDış platform sınırları:\n" + "\n".join(lines)
        )
