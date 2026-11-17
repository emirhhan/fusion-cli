"""Web işi araçları: site tarama ve görseli web için hazırlama.

Temel araç defterinde değil burada kayıtlıdır: web modellerine giden temel araç
istemi ölçülmüş bir bütçeyle sınırlı (`tests/test_tool_emulation_diet.py`).
Bu araçlar `generate_image` gibi motorun alan araçlarıdır.
"""

from __future__ import annotations

import asyncio
import base64
from urllib.parse import urljoin

from ...core.tool_content import ToolContent
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools import site_design as design
from ...tools.crawl import site_crawl
from ...tools.files import writable_path
from ...tools.image_ops import optimize_image
from ...tools.web import url_block_reason

_STRING = {"type": "string"}


async def run_site_design(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Sitenin tasarım sistemini ölç, varlıklarını indir, özetini modele ver."""
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return ToolResult.failure("'url' gerekli (ör. https://site.com).")
    url = url.strip() if url.startswith(("http://", "https://")) else f"https://{url.strip()}"
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    raw_pages = args.get("pages")
    extra = (
        tuple(urljoin(url, page) for page in raw_pages if isinstance(page, str) and page.strip())
        if isinstance(raw_pages, list)
        else ()
    )
    # Ek sayfalar da ana adres gibi denetlenir: mutlak `pages=["http://169.254.169.254/…"]`
    # iç ağ/metadata korumasını atlıyordu (A4-47).
    for page in extra:
        page_reason = url_block_reason(page)
        if page_reason is not None:
            return ToolResult.failure(f"Bu sayfaya erişilemez ({page}): {page_reason}")
    out = args.get("out")
    label = out.strip() if isinstance(out, str) and out.strip() else design.DEFAULT_FOLDER
    folder = writable_path(context, label)
    try:
        report = await design.measure(url, chrome=context.chrome, extra_pages=extra)
    except design.DesignError as error:
        return ToolResult.failure(f"Tasarım ölçülemedi: {error}")
    if not report.pages:
        return ToolResult.failure("Hiçbir sayfa açılamadı; adresi ve bağlantıyı kontrol et.")
    try:
        await design.download_assets(report, folder)
    except Exception as error:  # sınır: ağ/disk hatası aracı ham istisnayla düşürmesin (A4-48)
        return ToolResult.failure(
            f"Tasarım ölçüldü ama varlıklar indirilemedi ({type(error).__name__}): "
            f"{str(error)[:200]}"
        )
    first_shot = report.pages[0].get("_screenshot_bytes")
    await asyncio.to_thread(design.save_report, report, folder, label)
    content: tuple[ToolContent, ...] = ()
    if isinstance(first_shot, bytes | bytearray):
        content = (ToolContent.image("image/jpeg", base64.b64encode(first_shot).decode()),)
    return ToolResult(design.summarize(report, label), content=content)


async def run_play_probe(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tarayıcı oyununu başsız Chromium'da oynatıp tepkisini ölç."""
    from ...tools.files import resolve_path
    from ...tools.play_probe import MIN_RAF_PER_SECOND, parse_keys, probe_game

    hedef = args.get("target")
    if not isinstance(hedef, str) or not hedef.strip():
        return ToolResult.failure("'target' gerekli: index.html yolu ya da http adresi.")
    hedef = hedef.strip()
    if not hedef.startswith(("http://", "https://")):
        yol = resolve_path(context, hedef)
        if not await asyncio.to_thread(yol.is_file):
            return ToolResult.failure(f"Dosya yok: {hedef}")
        hedef = yol.as_uri()
    try:
        rapor = await probe_game(hedef, parse_keys(args.get("keys")))
    except ImportError:
        return ToolResult.failure("Playwright kurulu değil; oyun sondası çalışamadı.")
    except Exception as error:  # sınır: Chromium indirilmemiş vb. (A4-48)
        return ToolResult.failure(
            f"Oyun sondası çalışamadı ({type(error).__name__}): {str(error)[:200]}"
        )
    if (
        "oyun" not in context.task_kinds
        and rapor.state_before is None
        and rapor.state_after is None
        and rapor.restart_state is None
        and rapor.canvas_kind is None
        and rapor.canvas_changed is None
    ):
        # A completed tool call is not evidence that the page is a game. A
        # mistaken counter probe otherwise registered an irrelevant final gate,
        # which waited for game-over and demanded moving enemies on the counter.
        diagnostics = {
            "console_error_count": len(rapor.console_errors),
            "console_errors": list(rapor.console_errors[:3]),
            "raf_per_second": rapor.raf_per_second,
            "resource_notes": list(rapor.ignored_resources[:5]),
            "loaded_resource_count": len(rapor.asset_usage.loaded),
            "loaded_resources": [url[:500] for url in rapor.asset_usage.loaded[:20]],
        }
        page_ok = not rapor.console_errors and rapor.raf_per_second >= MIN_RAF_PER_SECOND
        lines = [
            "Bu sayfa oyun sondasının kapsamı dışında. Oyun durumu ve canvas gözlenmedi; "
            "görev de oyun istemiyor. Sayaç ve düğmeleri tarayıcı araçlarıyla doğrula.",
            f"Konsol hatası: {len(rapor.console_errors)}",
            *rapor.console_errors[:3],
            f"Tarayıcı rAF (ana iş parçacığı sağlığı): {rapor.raf_per_second}/sn",
        ]
        if rapor.raf_per_second < MIN_RAF_PER_SECOND:
            lines.append("Ana iş parçacığı yavaş: sayfanın tepkiselliği doğrulanamadı.")
        if rapor.ignored_resources:
            lines.extend(["Kaynak notları (sayfa hatası değil):", *rapor.ignored_resources[:5]])
        if rapor.asset_usage.loaded:
            lines.append(f"Yüklenen görsel kaynak: {len(rapor.asset_usage.loaded)}")
            lines.extend(url[:500] for url in rapor.asset_usage.loaded[:20])
        return ToolResult(
            "\n".join(lines),
            ok=page_ok,
            structured={"game_probe": "not_applicable", "page_diagnostics": diagnostics},
            is_observation=True,
        )
    context.probed_games.add(hedef)
    return ToolResult(f"Oyun sondası ({hedef}):\n{rapor.summary()}")


def web_work_tools() -> tuple[Tool, ...]:
    return (
        Tool(
            name="play_probe",
            description="Tarayıcı oyununu ayrı başsız tarayıcıda OYNAT: tuşlara basar, "
            "window.__GAME_STATE__ ve canvas değişimini, rAF'ı, konsol hatalarını ve R ile "
            "yeniden başlatmayı ölçer. Oyunun oynanabilirliğini doğrulamanın yolu budur; "
            "masaüstüne osascript ile tuş gönderme.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {**_STRING, "description": "index.html yolu ya da http adresi"},
                    "keys": {"type": "array", "items": _STRING},
                },
                "required": ["target"],
            },
            run=run_play_probe,
        ),
        Tool(
            name="site_design",
            description="Bir sitenin TASARIM SİSTEMİNİ ölç ve varlıklarını projeye indir: yazı "
            "tipleri (+dosyaları), renkler, tipografi ölçeği, düzen, bileşenler (kart, buton, "
            "fiyat, menü) ve görseller; ana, kategori, ürün ve sepet sayfalarını kendisi bulur. "
            "Fusion Browser bağlıysa kullanıcının Chrome'unu kullanır. Bir siteye BENZEYEN site "
            "yaparken tahmin etme, önce bunu çağır.",
            parameters={
                "type": "object",
                "properties": {
                    "url": _STRING,
                    "pages": {"type": "array", "items": _STRING},
                    "out": {
                        "type": "string",
                        "description": "varlık klasörü (varsayılan tasarim-kaynak)",
                    },
                },
                "required": ["url"],
            },
            run=run_site_design,
            mutating=True,
        ),
        Tool(
            name="site_crawl",
            description="Siteyi aynı alan adında gez (robots.txt'ye uyar): başlıklar ve "
            "görsel listesi. Tek sayfa için web_fetch.",
            parameters={
                "type": "object",
                "properties": {
                    "url": _STRING,
                    "max_pages": {"type": "integer"},
                    "max_depth": {"type": "integer"},
                },
                "required": ["url"],
            },
            run=site_crawl,
        ),
        Tool(
            name="optimize_image",
            description="Var olan görseli web için hazırla (.webp, isteğe bağlı tam ölçü, "
            "srcset) ve <img> önerisi ver.",
            parameters={
                "type": "object",
                "properties": {
                    "path": _STRING,
                    "out": _STRING,
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "alt": _STRING,
                    "ilk_ekran": {"type": "boolean"},
                },
                "required": ["path"],
            },
            run=optimize_image,
            mutating=True,
        ),
    )
