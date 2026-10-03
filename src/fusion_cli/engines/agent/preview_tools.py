"""`start_preview`: projeyi çalıştır, sayfayı aç, ölç ve kullanıcıya göster.

Ölçüldü (2 Ekim 2026, "sneaksup" sohbeti): kullanıcı önizleme istedi; Fusion MySQL +
WP-CLI + Docker rehberi yazdı, sonra açmadığı bir `preview.html` bıraktı. Oysa
bilgisayarda `php` ve `wp` kuruluydu. Bu araç o işi baştan sona yapar:

1. proje türünü dosyalardan anlar (WordPress, PHP, Node, statik),
2. WordPress çekirdeği yoksa SQLite ile kurar (MySQL gerekmez),
3. sunucuyu başlatır ve sayfayı açıp ölçer (HTTP, hata metni, iç bağlantılar,
   konsol, ekran görüntüsü),
4. masaüstü uygulamasında önizleme panelini adresle açar (`PreviewReady`).

Temel araç defterinde değil burada kayıtlıdır (bkz. `web_tools`): web modellerine
giden temel araç istemi ölçülmüş bir bütçeyle sınırlı.
"""

from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from ...core.events import PreviewReady, StatusChanged
from ...core.tool_content import ToolContent
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools import design_compare, preview_server, site_design
from ...tools.files import resolve_path
from ...tools.preview_probe import SCREENSHOT_HEIGHT, SCREENSHOT_WIDTH, PageProbe, probe
from ...tools.wordpress_setup import (
    WordPressSetup,
    WordPressSetupError,
    find_wp_cli,
    setup_wordpress,
)
from .php_verify import find_php_executable

if TYPE_CHECKING:
    from .loop import AgentDeps

_DESCRIPTION = (
    "Projeyi yerel sunucuda ÇALIŞTIR ve sayfayı aç: WordPress (çekirdek yoksa SQLite ile "
    "kendisi kurar), PHP, Node (dev/start) ya da statik HTML. Sayfayı ölçer (hata, boş "
    "sayfa, iç bağlantılar, ekran görüntüsü) ve kullanıcıya adresi gösterir. Kullanıcı "
    "görmek/önizlemek/çalıştırmak istediğinde ya da web işini bitirdiğinde bunu çağır; "
    "kurulum rehberi yazma. BOŞ klasörde WordPress sitesi başlatmak için kind='wordpress' "
    "ver (e-ticaret için plugins=['woocommerce']): wp/MySQL/Docker komutu yazma."
)
#: WordPress.org eklenti kısa adı (slug) biçimi; kabuğa giden argüman bununla sınırlanır.
_PLUGIN_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
#: Tek çağrıda kurulacak en fazla eklenti (her biri bir indirme + etkinleştirme).
MAX_PLUGINS = 8


def preview_tool(deps: AgentDeps) -> Tool:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        return await run_preview(deps, args, context)

    return Tool(
        name="start_preview",
        description=_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "çalıştırılacak klasör (varsayılan proje kökü)",
                },
                "page": {"type": "string", "description": "açılacak yol, ör. /shop/"},
                "kind": {
                    "type": "string",
                    "enum": ["wordpress"],
                    "description": "boş klasörde yeni WordPress sitesi kurup başlat",
                },
                "plugins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "kurulacak WordPress.org eklentileri, ör. ['woocommerce']",
                },
            },
        },
        run=_run,
        mutating=True,
        reruns_on_change=True,
    )


async def run_preview(deps: AgentDeps, args: ToolArgs, context: ToolContext) -> ToolResult:
    raw = args.get("path")
    root = resolve_path(context, raw) if isinstance(raw, str) and raw.strip() else context.root
    kind = preview_server.detect_kind(root)
    if kind is None and args.get("kind") == preview_server.PreviewKind.WORDPRESS.value:
        # Boş klasörde "önce WordPress'i kur" modelin doğal ilk adımıdır. Ölçüldü (2 Ekim,
        # 5. kabul koşusu): araç "önce temayı yaz" deyip reddedince model `wp config
        # create` + MySQL ile 10 dakika boğuştu ve tek tema dosyası yazamadı.
        await asyncio.to_thread((root / "wp-content" / "themes").mkdir, parents=True, exist_ok=True)
        kind = preview_server.PreviewKind.WORDPRESS
    if kind is None:
        return ToolResult.failure(
            f"{root} içinde henüz çalıştırılacak bir şey yok (index.html, index.php, "
            "wp-content/ ya da dev/start betikli package.json). WordPress sitesi için "
            "start_preview'ı kind='wordpress' ile çağır (e-ticaret: plugins=['woocommerce']): "
            "çekirdeği SQLite ile KENDİSİ kurar ve siteyi açar — wp core download, MySQL ya "
            "da Docker ile uğraşma. Diğer türlerde önce sayfayı yaz."
        )
    plugins = _plugin_slugs(args.get("plugins"))
    if isinstance(plugins, str):
        return ToolResult.failure(plugins)
    port = _port(root)
    setup: WordPressSetup | None = None
    try:
        if kind is preview_server.PreviewKind.WORDPRESS:
            setup = await _wordpress(deps, root, port, plugins)
        entry = preview_server.static_entry(root) or ""
        preview = await preview_server.start(
            root, kind, port, php=find_php_executable(), entry=entry
        )
    except (preview_server.PreviewError, WordPressSetupError) as error:
        return ToolResult.failure(f"Önizleme başlatılamadı: {error}")
    page = args.get("page")
    url = preview.url
    if isinstance(page, str) and page.strip():
        url = urljoin(preview.url, page.strip())
    kaynak = await asyncio.to_thread(site_design.reference_pages, root)
    sonuc = await probe(
        url,
        # Kaynak site ölçülmüşse aynı ölçüm yerel sayfada da yapılır ve farklar söylenir.
        measure_script=site_design.probe_script() if kaynak else None,
        viewport=(
            (site_design.VIEWPORT["width"], site_design.VIEWPORT["height"])
            if kaynak
            else (SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT)
        ),
    )
    preview.last_probe = {"ok": not sonuc.problems, "summary": sonuc.summary(), "url": url}
    deps.publisher.publish(
        PreviewReady(url=url, kind=kind.value, root=str(root), title=sonuc.title)
    )
    shot = await asyncio.to_thread(_save_screenshot, root, sonuc.screenshot)
    farklar = _differences(kaynak, sonuc)
    if farklar is not None:
        farklar = (*farklar, *await _product_page_differences(kaynak, sonuc))
    return _result(url, kind.value, sonuc, setup, shot, farklar)


#: Ürün ayrıntı sayfası sayılan iç bağlantı yolları (WooCommerce, Türkçe kalıcı bağlantı).
_PRODUCT_PATH = re.compile(r"/(?:product|urun)/[^/?#]+/?$")


async def _product_page_differences(
    kaynak: list[dict[str, Any]], sonuc: PageProbe
) -> tuple[str, ...]:
    """Kaynakta ürün sayfası ölçülmüşse sitenin bir ürün sayfasını da ölçüp karşılaştır.

    Ölçüldü (3 Ekim 2026, 11. kabul koşusu): son adımlarda `woocommerce.php` şablonu
    bozuldu ve her ürün sayfası "Shop" listesi göstermeye başladı; ana sayfa hatasızdı ve
    kapanış doğrulaması yalnız ona baktığı için iş "doğrulandı" diye bitti.
    """
    reference = next((page for page in kaynak if page.get("product")), None)
    if reference is None or (sonuc.measured or {}).get("product"):
        return ()
    link = next((item.url for item in sonuc.links if _PRODUCT_PATH.search(item.url)), None)
    if link is None:
        return ()
    urun = await probe(
        link,
        measure_script=site_design.probe_script(),
        viewport=(site_design.VIEWPORT["width"], site_design.VIEWPORT["height"]),
    )
    if urun.measured is None:
        return ()
    if not urun.measured.get("product"):
        baslik = (urun.measured.get("texts") or [{}])[0].get("text", "")
        return (
            f"ÜRÜN SAYFASI ({link}): kaynaktaki ürün sayfasında fiyat, galeri ve 'sepete "
            f"ekle' düğmesi var; bu sayfada ürün ölçülemedi (ilk başlık '{baslik}'). "
            "Ürün şablonu yanlış/bozuk olabilir.",
        )
    return tuple(f"{fark} [{link}]" for fark in design_compare.compare(reference, urun.measured))


def _differences(kaynak: list[dict[str, Any]], sonuc: PageProbe) -> tuple[str, ...] | None:
    """Kaynak ölçümle farklar; karşılaştırılacak kaynak sayfa yoksa None."""
    if not kaynak or sonuc.measured is None:
        return None
    reference = design_compare.pick_reference(kaynak, sonuc.measured)
    if reference is None:
        return None
    farklar = list(design_compare.compare(reference, sonuc.measured))
    kaynak_host = urlparse(str(kaynak[0].get("url", ""))).netloc.removeprefix("www.")
    if kaynak_host and any(
        host.removeprefix("www.").endswith(kaynak_host) for host in sonuc.external_hosts
    ):
        # Ölçüldü (16. kabul koşusu): model sepet/favori işlemlerini kaynak sitenin canlı
        # API'sine bağladı; site kendi WooCommerce'i yerine başkasının sunucusuyla konuşuyordu.
        farklar.insert(
            0,
            f"KAYNAK SİTEYE İSTEK: sayfan {kaynak_host} alan adına istek atıyor. Kopya kendi "
            "WordPress/WooCommerce'iyle çalışmalı; kaynak sitenin betik/API çağrılarını kaldır.",
        )
    return (str(reference.get("url", "")), *farklar)


#: Son önizleme ekran görüntüsü (proje içinde): görsel okuyamayan model `view_image` ile
#: bakabilsin, kullanıcı da açıp görebilsin.
SCREENSHOT_FILE = Path(".fusion") / "onizleme.jpg"


def _save_screenshot(root: Path, data: bytes | None) -> str:
    if not data:
        return ""
    try:
        target = root / SCREENSHOT_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError:
        return ""
    return SCREENSHOT_FILE.as_posix()


async def _wordpress(
    deps: AgentDeps, root: Path, port: int, plugins: tuple[str, ...]
) -> WordPressSetup:
    if preview_server.needs_wordpress_setup(root):
        deps.publisher.publish(
            StatusChanged("WordPress kuruluyor (SQLite, MySQL gerekmez) — ~30 sn…")
        )
    return await setup_wordpress(
        root, f"http://127.0.0.1:{port}", wp_cli=find_wp_cli(), plugins=plugins
    )


def _plugin_slugs(raw: object) -> tuple[str, ...] | str:
    """İstenen eklenti adları; geçersizse modele gidecek hata metni."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > MAX_PLUGINS:
        return f"'plugins' en fazla {MAX_PLUGINS} eklenti adından oluşan bir liste olmalı."
    slugs = tuple(item.strip().lower() for item in raw if isinstance(item, str))
    bad = [slug for slug in slugs if not _PLUGIN_SLUG.fullmatch(slug)]
    if bad or len(slugs) != len(raw):
        return (
            "'plugins' WordPress.org eklenti kısa adları olmalı (ör. 'woocommerce'); "
            f"geçersiz: {', '.join(bad) or 'metin olmayan öğe'}."
        )
    return slugs


def _port(root: Path) -> int:
    running = preview_server.running(root)
    if running is not None:
        port = urlparse(running.url).port
        if port is not None:
            return port
    return preview_server.free_port()


def _result(
    url: str,
    kind: str,
    sonuc: PageProbe,
    setup: WordPressSetup | None,
    shot: str = "",
    differences: tuple[str, ...] | None = None,
) -> ToolResult:
    lines = [f"Önizleme çalışıyor: {url} ({kind}). Kullanıcı bu adresi açabilir."]
    if setup is not None and setup.steps:
        lines.append("Kurulum: " + "; ".join(setup.steps) + ".")
    if setup is not None and setup.credentials is not None:
        panel = urljoin(url, "/wp-admin/")
        lines.append(
            f"Yönetici paneli: {panel} — kullanıcı adı ve parola "
            f"`.fusion/{setup.credentials.name}` dosyasında (parolayı sohbete yazma)."
        )
    lines.append(f"Ölçüm: {sonuc.summary()}.")
    problems = [*(setup.problems if setup is not None else ()), *sonuc.problems]
    konsol = [
        error
        for error in sonuc.console_errors
        # Yüklenemeyen kaynaklar yukarıda ADIYLA listelendi; adsız konsol satırı tekrar olur.
        if not (sonuc.failed_resources and "Failed to load resource" in error)
    ]
    problems.extend(f"konsol hatası: {error}" for error in konsol[:5])
    if problems:
        lines.append("SORUNLAR (düzelt ve start_preview'ı tekrar çağır):")
        lines.extend(f"- {problem}" for problem in problems)
    else:
        lines.append("Sayfa hatasız açıldı. Ekran görüntüsü ekte; tasarımı istekle karşılaştır.")
    if shot:
        lines.append(f"Ekran görüntüsü dosyası: {shot}")
    if differences is not None:
        kaynak_url, *farklar = differences
        if farklar:
            lines.append(
                f"KAYNAKLA FARKLAR ({kaynak_url} ile aynı ölçümle karşılaştırıldı) — düzelt ve "
                "start_preview'ı tekrar çağır:"
            )
            lines.extend(f"- {fark}" for fark in farklar)
        else:
            lines.append(
                f"Kaynakla ({kaynak_url}) ölçülerek karşılaştırıldı: belirgin fark bulunmadı."
            )
    content: tuple[ToolContent, ...] = ()
    if sonuc.screenshot:
        content = (ToolContent.image("image/jpeg", base64.b64encode(sonuc.screenshot).decode()),)
    # Sayfa açıldıysa araç başarılıdır; sorunlar metinde düzeltilmek üzere listelenir.
    return ToolResult("\n".join(lines), ok=0 < sonuc.status < 400, content=content)
