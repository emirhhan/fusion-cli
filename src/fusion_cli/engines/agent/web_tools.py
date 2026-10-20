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
    out = args.get("out")
    label = out.strip() if isinstance(out, str) and out.strip() else design.DEFAULT_FOLDER
    folder = writable_path(context, label)
    try:
        report = await design.measure(url, chrome=context.chrome, extra_pages=extra)
    except design.DesignError as error:
        return ToolResult.failure(f"Tasarım ölçülemedi: {error}")
    if not report.pages:
        return ToolResult.failure("Hiçbir sayfa açılamadı; adresi ve bağlantıyı kontrol et.")
    await design.download_assets(report, folder)
    first_shot = report.pages[0].get("_screenshot_bytes")
    await asyncio.to_thread(design.save_report, report, folder, label)
    content: tuple[ToolContent, ...] = ()
    if isinstance(first_shot, bytes | bytearray):
        content = (ToolContent.image("image/jpeg", base64.b64encode(first_shot).decode()),)
    return ToolResult(design.summarize(report, label), content=content)


async def run_play_probe(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tarayıcı oyununu başsız Chromium'da oynatıp tepkisini ölç."""
    from ...tools.files import resolve_path
    from ...tools.play_probe import parse_keys, probe_game

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
