"""Kullanıcının izin verdiği açık Chrome sekmesine bağlı araçlar."""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import mimetypes
import re
import weakref
from typing import Any

from ..core.constants import MAX_UPLOAD_BYTES
from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolEffect, ToolResult
from .args import require_str
from .web import url_block_reason


async def _call(context: ToolContext, name: str, data: dict[str, Any]) -> ToolResult:
    if context.chrome is None:
        return ToolResult.failure(
            "Chrome bağlantısı yalnız Fusion masaüstü uygulamasında kullanılabilir."
        )
    try:
        result = await context.chrome.invoke(name, data)
    except (ConnectionError, TimeoutError) as exc:
        return ToolResult.failure(str(exc))
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("hata") or "Chrome komutu başarısız."))
    return ToolResult(json.dumps(result.get("veri", {}), ensure_ascii=False))


async def chrome_page(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı sekmeyi oku; `query` verilirse metne/etikete göre öğe bul (ref al)."""
    query = args.get("query")
    if isinstance(query, str) and query.strip():
        return await _call(context, "find", {"query": query.strip()})
    return await _call(context, "snapshot", {})


async def chrome_assets(_args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı sekmedeki görselleri (gerçek ölçüleriyle), arka planları ve paleti topla."""
    return await _call(context, "assets", {})


#: Tıklama sayfada iz bırakmadığında modele eklenen not. Otomatik yeniden tıklama
#: YAPILMAZ: "sepete ekle", "gönder" gibi işlemler iki kez çalışabilir.
NO_CHANGE_NOTE = (
    "NOT: Tıklamadan sonra sayfada görünür bir değişiklik olmadı (adres, metin, açılır "
    "pencere, seçim aynı). Öğe doğru mu? chrome_page ile yeniden oku; gerekirse farklı "
    "öğeyi ya da screenshot + click_at dene. Aynı tıklamayı körlemesine tekrarlama."
)


def with_action_check(result: ToolResult) -> ToolResult:
    """Eylem sonucu `changed: false` taşıyorsa modele açık not ekle."""
    if not result.ok:
        return result
    try:
        veri = json.loads(result.output)
    except json.JSONDecodeError:
        return result
    if isinstance(veri, dict) and veri.get("changed") is False:
        return ToolResult(f"{result.output}\n{NO_CHANGE_NOTE}")
    return result


async def chrome_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    return with_action_check(await _call(context, "click", {"ref": require_str(args, "ref")}))


async def chrome_type(args: ToolArgs, context: ToolContext) -> ToolResult:
    result = await _call(
        context, "type", {"ref": require_str(args, "ref"), "text": require_str(args, "text")}
    )
    if not result.ok:
        return result
    with contextlib.suppress(json.JSONDecodeError):
        veri = json.loads(result.output)
        if isinstance(veri, dict) and veri.get("verified") is False:
            return ToolResult.failure(
                "Yazılan metin alana oturmadı (iki yöntem denendi). Alandaki değer: "
                f"{veri.get('value', '')!r}. Alanı chrome_page ile yeniden oku; maskeli ya da "
                "özel bir editörse önce tıklayıp odakla, sonra tekrar yaz."
            )
    return result


#: Son ekran görüntüsünün ölçeği (sayfa CSS pikseli / görüntü pikseli), bağlantı başına.
#: `click_at` görüntü koordinatını bununla sayfa ölçeğine çevirir.
_SCREENSHOT_SCALES: weakref.WeakKeyDictionary[object, float] = weakref.WeakKeyDictionary()

#: Sayfada kalıcı iz BIRAKMAYAN işlemler: otomatik kipte sorulmaz, plan kipinde serbest.
#: Seçim kutusu değeri yalnız formu değiştirir; gönderme ayrı bir tıklama/Enter'dır.
_READ_ACTIONS = frozenset(
    {
        "scroll", "wait", "tabs", "open", "tab", "select", "screenshot",
        "back", "forward", "reload", "close", "hover", "text", "assets",
    }
)  # fmt: skip

#: Tıklanınca geri dönüşü zor ya da dışa dönük iş yapan düğme adları (TR/EN).
#: Claude in Chrome da gezinmeyi ve sıradan tıklamayı sormaz; göndermede durur.
#:
#: Fiiller KELİME olarak aranır. Ölçüldü (27 Eylül): Instagram gönderi kartının
#: adı "1.234 beğenme, 12 yorum" içeriyor; alt dize araması bunu "beğen" sanıp
#: salt okuma turunu izin sorusunda durduruyordu.
_RISKY_CLICK = re.compile(
    r"\b(?:gönder|paylaş|yayınla|yayımla|sil|silin|kaldır|satın al|ödeme yap|öde|"
    r"siparişi tamamla|siparişi onayla|onayla|kaydet|uygula|etkinleştir|devre dışı bırak|"
    r"duraklat|yorum yap|yanıtla|takip et|beğen|abone ol|"
    r"submit|send|post|publish|share|delete|remove|buy|purchase|pay|checkout|"
    r"confirm|save|apply|enable|disable|pause|follow|like|reply|comment)\b",
    re.IGNORECASE,
)

#: Bağlantı olsa bile oturumu kapatan tıklamalar sorulur.
_LOGOUT_LINK = re.compile(r"çıkış yap|oturumu kapat|log ?out|sign ?out", re.IGNORECASE)


async def chrome_action_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Kaydırma, bekleme, sekme ve seçim salt okuma sayılır; tuş (Enter formu gönderir) sorulur.

    Koordinata tıklama (`click_at`) ref'li tıklamayla aynı kuralla denetlenir: noktadaki
    öğenin adı okunur, gönder/sil/satın al gibiyse sorulur.
    """
    if args.get("action") == "click_at":
        point = _point(args.get("value"), context)
        if point is None or context is None or context.chrome is None:
            return None
        try:
            result = await context.chrome.invoke("describe_at", {"x": point[0], "y": point[1]})
        except (ConnectionError, TimeoutError):
            return None
        return _click_effect(result)
    return ToolEffect.REMOTE_READ if args.get("action") in _READ_ACTIONS else None


async def chrome_read_effect(_args: ToolArgs, _context: ToolContext | None) -> ToolEffect:
    """Gezinme ve alana yazma kalıcı iz bırakmaz: gönderme ayrı bir eylemdir."""
    return ToolEffect.REMOTE_READ


async def chrome_click_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Tıklanacak öğenin adına bak: gönder/sil/satın al gibi ise sor, değilse sorma.

    Ad okunamazsa `None` döner ve aracın kendi (sorulan) etkisi geçerli olur.
    """
    ref = args.get("ref")
    if context is None or context.chrome is None or not isinstance(ref, str):
        return None
    try:
        result = await context.chrome.invoke("describe", {"ref": ref})
    except (ConnectionError, TimeoutError):
        return None
    return _click_effect(result)


def _click_effect(result: dict[str, Any]) -> ToolEffect | None:
    """`describe` sonucundan tıklamanın etkisini çıkar; okunamazsa `None` (sorulur)."""
    veri = result.get("veri") if result.get("ok") else None
    if not isinstance(veri, dict):
        return None
    ad = f"{veri.get('name', '')} {veri.get('type', '')}"
    if veri.get("link") and not veri.get("submit"):
        # Gerçek adrese giden bağlantı yalnız gezinir; iş yapan şey sonraki sayfadaki
        # düğmedir ve o ayrıca denetlenir. Tek istisna oturumu kapatmak.
        return None if _LOGOUT_LINK.search(ad) else ToolEffect.REMOTE_READ
    if veri.get("submit") or _RISKY_CLICK.search(ad):
        return None
    return ToolEffect.REMOTE_READ


async def chrome_action(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tek araçta yardımcı sayfa işlemleri (Claude'daki gibi `action` alanıyla)."""
    action = require_str(args, "action")
    ref = args.get("ref")
    value = args.get("value")
    data: dict[str, Any] = {}
    if isinstance(ref, str) and ref:
        data["ref"] = ref
    if action == "scroll":
        data["direction"] = "up" if value == "up" else "down"
        return await _call(context, "scroll", data)
    if action == "wait":
        if not isinstance(value, str) or not value.strip():
            return ToolResult.failure("wait için 'value' alanına beklenecek metni yaz.")
        return await _call(context, "wait", {"text": value, "timeout_ms": 20_000})
    if action == "key":
        data["key"] = value if isinstance(value, str) and value else "Enter"
        return with_action_check(await _call(context, "key", data))
    if action == "screenshot":
        return await chrome_screenshot(args, context)
    if action == "tabs":
        return await _call(context, "tabs", {})
    if action == "open":
        if not isinstance(value, str) or not value.strip():
            return ToolResult.failure("open için 'value' alanına adresi yaz.")
        url = value if value.startswith(("https://", "http://")) else f"https://{value}"
        reason = url_block_reason(url)
        if reason is not None:
            return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
        return await _call(context, "tab_open", {"url": url})
    if action == "tab":
        if not isinstance(value, str) or not value.strip().isdigit():
            return ToolResult.failure(
                "tab için 'value' alanına 'tabs' çıktısındaki sekme id'sini yaz."
            )
        return await _call(context, "tab_select", {"id": int(value)})
    if action == "select":
        if "ref" not in data or not isinstance(value, str):
            return ToolResult.failure("select için 'ref' ve 'value' gerekli.")
        return await _call(context, "select", {**data, "value": value})
    if action in {"back", "forward", "reload"}:
        return await _call(context, "history", {"dir": action})
    if action == "close":
        if not isinstance(value, str) or not value.strip().isdigit():
            return ToolResult.failure("close için 'value' alanına sekme id'sini yaz.")
        return await _call(context, "tab_close", {"id": int(value)})
    if action == "hover":
        if "ref" not in data:
            return ToolResult.failure("hover için 'ref' gerekli.")
        return await _call(context, "hover", data)
    if action == "text":
        page = int(value) if isinstance(value, str) and value.strip().isdigit() else 1
        return await _call(context, "text_page", {"page": max(1, page)})
    if action == "click_at":
        point = _point(value, context)
        if point is None:
            return ToolResult.failure(
                "click_at için 'value' alanına ekran görüntüsündeki 'x,y' yaz."
            )
        return with_action_check(await _call(context, "click_at", {"x": point[0], "y": point[1]}))
    if action == "upload":
        return await _upload(data, value, context)
    if action == "assets":
        return await chrome_assets(args, context)
    return ToolResult.failure(
        "action: scroll, wait, key, select, tabs, open, tab, screenshot, back, forward, "
        "reload, close, hover, text, click_at, upload ya da assets olmalı."
    )


def _point(value: object, context: ToolContext | None) -> tuple[float, float] | None:
    """Ekran görüntüsü koordinatını ('x,y') sayfanın CSS pikseline çevir.

    Görüntü Retina'da iki kat piksel gelir; ölçek son ekran görüntüsünden
    (`chrome_screenshot`) köprüye yazılır. Ekran görüntüsü yoksa ölçek 1'dir.
    """
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*", value)
    if match is None:
        return None
    chrome = context.chrome if context is not None else None
    try:
        scale = _SCREENSHOT_SCALES.get(chrome, 1.0) if chrome is not None else 1.0
    except TypeError:
        scale = 1.0
    return round(float(match.group(1)) * scale, 1), round(float(match.group(2)) * scale, 1)


async def chrome_navigate(args: ToolArgs, context: ToolContext) -> ToolResult:
    url = require_str(args, "url")
    if not url.startswith(("https://", "http://")):
        url = f"https://{url}"
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    return await _call(context, "navigate", {"url": url})


async def chrome_screenshot(_args: ToolArgs, context: ToolContext) -> ToolResult:
    if context.chrome is None:
        return ToolResult.failure("Chrome eklentisi bağlı değil.")
    try:
        result = await context.chrome.invoke("screenshot", {})
    except (ConnectionError, TimeoutError) as exc:
        return ToolResult.failure(str(exc))
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("hata") or "Ekran görüntüsü alınamadı."))
    data = result.get("veri")
    image = data.get("image") if isinstance(data, dict) else None
    if not isinstance(image, str) or not image.startswith("data:image/jpeg;base64,"):
        return ToolResult.failure("Chrome geçersiz görsel döndürdü.")
    encoded = image.partition(",")[2]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return ToolResult.failure("Chrome görseli çözülemedi.")
    if len(decoded) > 3_000_000:
        return ToolResult.failure("Chrome görseli çok büyük.")
    size = jpeg_size(decoded)
    css_width = data.get("width") if isinstance(data, dict) else None
    note = "İzinli Chrome sekmesinin ekran görüntüsü."
    if size is not None and isinstance(css_width, int) and css_width > 0:
        # click_at görüntü koordinatı alır; köprü onu sayfa ölçeğine çevirir.
        with contextlib.suppress(TypeError):
            _SCREENSHOT_SCALES[context.chrome] = css_width / size[0]
        note += f" Görüntü {size[0]}x{size[1]} px; tıklamak için chrome_action click_at 'x,y'."
    return ToolResult(note, content=(ToolContent.image("image/jpeg", encoded),))


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """JPEG başlığından (SOF işareti) genişlik ve yüksekliği oku; okunamazsa `None`."""
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        if marker in {0xC0, 0xC1, 0xC2}:
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        index += 2 + length
    return None


async def _upload(data: dict[str, Any], value: object, context: ToolContext) -> ToolResult:
    """Projedeki dosyaları sayfanın dosya seçme alanına koy (göndermez)."""
    if "ref" not in data or not isinstance(value, str) or not value.strip():
        return ToolResult.failure(
            "upload için 'ref' (dosya alanı) ve 'value' (dosya yolları) gerekli."
        )
    from .files import resolve_path

    files: list[dict[str, str]] = []
    toplam = 0
    for raw in (part.strip() for part in value.split(",") if part.strip()):
        path = resolve_path(context, raw)
        if not path.is_file():
            return ToolResult.failure(f"Dosya yok: {raw}")
        icerik = path.read_bytes()
        toplam += len(icerik)
        if toplam > MAX_UPLOAD_BYTES:
            return ToolResult.failure(
                f"Yükleme sınırı aşıldı ({MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."
            )
        files.append(
            {
                "name": path.name,
                "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "data": base64.b64encode(icerik).decode("ascii"),
            }
        )
    return await _call(context, "upload", {**data, "files": files})
