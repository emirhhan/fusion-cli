"""Kullanıcının izin verdiği açık Chrome sekmesine bağlı araçlar."""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import mimetypes
import re
import weakref
from collections.abc import Mapping
from typing import Any

from ..core.constants import MAX_UPLOAD_BYTES
from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolEffect, ToolResult
from . import chrome_guard, chrome_images, chrome_inspect, chrome_record
from .args import require_str
from .chrome_claude_args import limit_output, parse_modifiers, tabs_create_if_empty
from .chrome_inspect import MONITOR_LIMIT, NETWORK_IDLE_VALUES
from .key_spec import key_base
from .preview_origins import allowed_local
from .risk_words import LOGOUT_PATTERN, RISKY_ACTION_PATTERN
from .web import browser_block_reason

__all__ = ["MONITOR_LIMIT", "NETWORK_IDLE_VALUES"]

#: Sayfayı değiştirmeyen eklenti komutları; zaman aşımında yalnız okuma başarısız olmuştur.
_READ_ONLY_OPERATIONS = frozenset(
    {
        "find", "snapshot", "assets", "tabs", "text_page", "describe", "wait", "screenshot",
        "tree", "console", "network", "shortcuts", "shortcut_run",
    }
)  # fmt: skip
#: Eylem komutunun sonucu gelmediğinde döndürülen metnin başı (izlenebilir ve test edilebilir).
UNKNOWN_OUTCOME_PREFIX = "SONUÇ BİLİNMİYOR:"


async def _call(context: ToolContext, name: str, data: dict[str, Any]) -> ToolResult:
    if context.chrome is None:
        return ToolResult.failure(
            "Chrome bağlantısı yalnız Fusion masaüstü uygulamasında kullanılabilir."
        )
    try:
        result = await context.chrome.invoke(name, data)
    except TimeoutError as exc:
        if name in _READ_ONLY_OPERATIONS:
            return ToolResult.failure(str(exc))
        # Komut eklentiye ulaştı ama sonucu gelmedi: sayfada çalışmış OLABİLİR. "Olmadı"
        # demek modeli aynı tıklamayı/gönderimi tekrarlamaya iter (iki kez sepete ekleme).
        return ToolResult.failure(
            f"{UNKNOWN_OUTCOME_PREFIX} '{name}' komutu tarayıcıya gönderildi ama sonucu "
            "gelmedi; sayfada etkisi olmuş olabilir. Aynı işlemi tekrar etmeden önce "
            "read_page ile sayfayı yeniden oku ve işlemin olup olmadığını kontrol et."
        )
    except ConnectionError as exc:
        return ToolResult.failure(str(exc))
    except (ValueError, RuntimeError, OSError) as exc:
        # Köprüden ham `JSONDecodeError`/`RuntimeError` çıkmasın (ölçüldü, 30 Ekim).
        return ToolResult.failure(f"Chrome köprüsü hatası: {type(exc).__name__}: {exc}")
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("hata") or "Chrome komutu başarısız."))
    return ToolResult(json.dumps(result.get("veri", {}), ensure_ascii=False))


async def chrome_page(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı sekmeyi oku; `query` ile öğe bul (ref al); `tree` ile erişilebilirlik ağacı.

    `tree=all|interactive` Claude'un read_page'i gibi girintili rol/ad/durum ağacı verir;
    `depth` seviye sınırı, `ref` yalnız o öğenin alt ağacı (P-043).
    """
    query = args.get("query")
    if isinstance(query, str) and query.strip():
        return await _call(context, "find", {"query": query.strip()})
    if args.get("tree"):
        tree = chrome_inspect.format_tree(
            await _call(context, "tree", chrome_inspect.tree_args(args))
        )
        return limit_output(tree, args.get("max_chars"))
    return limit_output(await _call(context, "snapshot", {}), args.get("max_chars"))


async def chrome_assets(_args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı sekmedeki görselleri (gerçek ölçüleriyle), arka planları ve paleti topla."""
    return await _call(context, "assets", {})


#: Tıklama sayfada iz bırakmadığında modele eklenen not. Otomatik yeniden tıklama
#: YAPILMAZ: "sepete ekle", "gönder" gibi işlemler iki kez çalışabilir.
NO_CHANGE_NOTE = (
    "NOT: Tıklamadan sonra sayfada görünür bir değişiklik olmadı (adres, metin, açılır "
    "pencere, seçim aynı). Öğe doğru mu? read_page ile yeniden oku; gerekirse farklı "
    "öğeyi ya da computer screenshot + coordinate ile left_click dene. Aynı tıklamayı "
    "körlemesine tekrarlama."
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


async def _prohibited(
    context: ToolContext, operation: str, data: dict[str, Any]
) -> ToolResult | None:
    """Her kipte yasak eylem (#422): öğe satın alma/hesap oluşturma/CAPTCHA ise çalıştırma."""
    reason = chrome_guard.prohibited_reason(
        chrome_guard.described(await _describe(context, operation, data))
    )
    return None if reason is None else ToolResult.failure(reason)


async def chrome_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    ref = require_str(args, "ref")
    refused = await _prohibited(context, "describe", {"ref": ref})
    if refused is not None:
        return refused
    return with_action_check(await _call(context, "click", {"ref": ref}))


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
                f"{veri.get('value', '')!r}. Alanı read_page ile yeniden oku; maskeli ya da "
                "özel bir editörse önce tıklayıp odakla, sonra tekrar yaz."
            )
    return result


#: Son ekran görüntüsünün ölçeği (sayfa CSS pikseli / görüntü pikseli), bağlantı başına.
#: `click_at` görüntü koordinatını bununla sayfa ölçeğine çevirir.
_SCREENSHOT_SCALES: weakref.WeakKeyDictionary[object, float] = weakref.WeakKeyDictionary()

#: Sayfayı YALNIZ okuyan işlemler: hiçbir kipte sorulmaz, plan kipinde serbest.
#: `window` yeni pencere açar ve `open` gibi yalnız gezinir; `record` BURADA DEĞİL.
_READ_ACTIONS = frozenset(
    {
        "scroll", "wait", "tabs", "open", "new_tab", "tab", "screenshot",
        "back", "forward", "reload", "hover", "text", "assets", "wheel", "zoom",
        "console", "network", "shortcuts", "shortcut", "window",
    }
)  # fmt: skip
#: Sayfayla etkileşen ama kalıcı iz bırakmayan işlemler: otomatik kipte sorulmaz.
#: Seçim kutusu değeri yalnız formu değiştirir; gönderme ayrı bir tıklama/Enter'dır.
#: Sekme gruplama kullanıcının sekme düzenini değiştirir ama veri kaybettirmez.
#:
#: Ölçüldü (31 Ekim, bağımsız inceleme): `record` okuma sayılıyordu ve plan/Manuel kipte
#: sorulmadan geçiyordu. `start` ekranı 60 sn boyunca sürekli yakalar, `stop` proje
#: köküne (`.fusion/kayitlar`) GIF yazar; plan kipi hiçbir şey yazmamalı, Manuel kip
#: sormalı. Tek karelik `screenshot` okuma kalır. Otomatik kipte sorulmaz: dosya proje
#: kökünde ve `writable_path` denetiminden geçer.
_INTERACT_ACTIONS = frozenset({"select", "check", "type_focused", "resize", "group", "record"})

#: Enter'ın mesaj/yorum GÖNDERDİĞİ alanlar (ad, yer tutucu ya da form düğmesi).
_MESSAGE_FIELD = re.compile(r"\b(?:mesaj|message|sohbet|chat|dm)\b", re.IGNORECASE)

#: Riskli düğme ve çıkış bağlantısı sözcükleri masaüstüyle ortaktır (`tools.risk_words`, P-008).
_RISKY_CLICK = RISKY_ACTION_PATTERN
_LOGOUT_LINK = LOGOUT_PATTERN


async def chrome_action_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Kaydırma, bekleme ve sekme okumadır; seçim, tuş ve ekran kaydı etkileşimdir.

    Koordinata tıklama (`click_at`) ref'li tıklamayla aynı kuralla denetlenir: noktadaki
    öğenin adı okunur, gönder/sil/satın al gibiyse sorulur. Enter yalnız mesaj/yorum
    kutusunda ya da riskli düğmeli formda sorulur (`_key_effect`).
    """
    action = args.get("action")
    if action == "close":
        # Sekme kapatma kaydedilmemiş kullanıcı verisini kaybettirebilir.
        return ToolEffect.REMOTE_DESTRUCTIVE
    if action == "right_click":
        # Bağlam menüsü açar; tıklama gibi iş yapmaz.
        return ToolEffect.REMOTE_INTERACT
    if action == "drag":
        return ToolEffect.REMOTE_INTERACT
    if action in {"click_at", "double_click", "triple_click"}:
        ref = args.get("ref")
        if context is None or context.chrome is None:
            return None
        if isinstance(ref, str) and ref:
            result = await _describe(context, "describe", {"ref": ref})
            return None if result is None else _click_effect(result)
        point = _point(args.get("value"), context)
        if point is None:
            return None
        result = await _describe(context, "describe_at", {"x": point[0], "y": point[1]})
        return None if result is None else _click_effect(result)
    if action == "key":
        return await _key_effect(args, context)
    if action == "type_focused":
        return await chrome_type_effect({}, context)
    if action in _INTERACT_ACTIONS:
        return ToolEffect.REMOTE_INTERACT
    return ToolEffect.REMOTE_READ if action in _READ_ACTIONS else None


async def chrome_read_effect(_args: ToolArgs, _context: ToolContext | None) -> ToolEffect:
    """Gezinme yalnız okur."""
    return ToolEffect.REMOTE_READ


async def chrome_type_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect:
    """Alana yazma kalıcı iz bırakmaz: gönderme ayrı bir eylemdir.

    Hassas alan (parola, kart, kimlik numarası) her kipte sorulur (#422: "Inputting
    potentially sensitive information into websites" izin kipinden bağımsız onay ister).
    """
    ref = args.get("ref")
    if context is None or context.chrome is None:
        return ToolEffect.REMOTE_INTERACT
    data = {"ref": ref} if isinstance(ref, str) and ref else {}
    veri = chrome_guard.described(
        await _describe(context, "describe" if data else "describe_key", data)
    )
    if chrome_guard.sensitive_field_reason(veri) is not None:
        return ToolEffect.REMOTE_DESTRUCTIVE
    return ToolEffect.REMOTE_INTERACT


#: Enter'ın aileleri: değiştirici ile (Meta/Ctrl+Enter) Gmail/Slack'te mesajı GÖNDERİR.
_ENTER_KEYS = frozenset({"enter", "return", "numpadenter"})
#: Alan dışında seçili öğeyi silen tuşlar.
_DELETE_KEYS = frozenset({"delete", "backspace"})


def _key_base(key: str) -> str:
    """'Meta+Enter' → 'enter': masaüstüyle ortak ayrıştırıcı (`tools.key_spec`)."""
    return key_base(key)


async def _key_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Tab/ok/Escape iz bırakmaz; Enter'ın ne yapacağı odaktaki alana bakılarak anlaşılır.

    Değiştiricili Enter (Meta/Ctrl/Shift+Enter) çıplak Enter gibi, Delete/Backspace
    ise alan dışında silme olarak değerlendirilir (T1-16).

    Ölçüldü (2 Ekim, kullanıcı): otomatik kipte arama kutusuna yazıp Enter'a basmak
    bile soruluyordu. Arama kutusunda Enter gezinmedir; mesaj/yorum kutusunda ya da
    "Gönder/Satın al" düğmeli formda göndermedir ve sorulur.
    """
    key = args.get("value")
    base = _key_base(key) if isinstance(key, str) and key else "enter"
    if base not in _ENTER_KEYS and base not in _DELETE_KEYS:
        return ToolEffect.REMOTE_INTERACT
    if context is None or context.chrome is None:
        return None
    ref = args.get("ref")
    result = await _describe(context, "describe_key", {"ref": ref} if isinstance(ref, str) else {})
    veri = result.get("veri") if result is not None and result.get("ok") else None
    if not isinstance(veri, dict):
        return None
    if base in _DELETE_KEYS:
        # Yazı alanında Delete/Backspace yazmadır; alan dışında seçili öğeyi (e-posta,
        # dosya, kart) siler.
        return ToolEffect.REMOTE_INTERACT if veri.get("editable") else None
    if veri.get("search"):
        return ToolEffect.REMOTE_INTERACT
    ipucu = f"{veri.get('name', '')} {veri.get('hint', '')} {veri.get('submit_name', '')}"
    if veri.get("editable") or _RISKY_CLICK.search(ipucu) or _MESSAGE_FIELD.search(ipucu):
        return None
    return ToolEffect.REMOTE_INTERACT


async def _describe(
    context: ToolContext, operation: str, data: dict[str, Any]
) -> dict[str, Any] | None:
    """Eklentiden öğe tarifini al; bağlantı yoksa None (çağrı sorulur)."""
    if context.chrome is None:
        return None
    try:
        return await context.chrome.invoke(operation, data)
    except (ConnectionError, TimeoutError):
        return None


async def chrome_click_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Tıklanacak öğenin adına bak: gönder/sil/satın al gibi ise sor, değilse sorma.

    Ad okunamazsa `None` döner ve aracın kendi (sorulan) etkisi geçerli olur.
    """
    ref = args.get("ref")
    if context is None or context.chrome is None or not isinstance(ref, str):
        return None
    result = await _describe(context, "describe", {"ref": ref})
    return None if result is None else _click_effect(result)


def click_is_risky(result: dict[str, Any]) -> bool:
    """`describe` sonucuna göre tıklama gönder/sil/satın al gibi mi (ya da okunamadı mı).

    Kit → Chrome yolu (`appserver/kits_browser_routes.py`) onay penceresini bununla
    uyarır; Fusion'ın kendi araçlarıyla aynı sınıflandırma, ikinci bir liste yok.
    """
    return _click_effect(result) is None


def key_is_risky(key: str, veri: Mapping[str, Any] | None) -> bool:
    """Tuşun kalıcı iş yapma olasılığı: `_key_effect` ile aynı kural, araç bağlamı olmadan.

    Enter/Delete dışındaki tuşlar iz bırakmaz. Enter arama kutusunda gezinir; yazı
    alanında, mesaj kutusunda ya da riskli düğmeli formda gönderir. Delete yazı alanı
    dışında seçili öğeyi siler. Odak okunamadıysa (`veri` yok) riskli sayılır.
    """
    base = _key_base(key) if key.strip() else "enter"
    if base not in _ENTER_KEYS and base not in _DELETE_KEYS:
        return False
    if not isinstance(veri, Mapping):
        return True
    if base in _DELETE_KEYS:
        return not veri.get("editable")
    if veri.get("search"):
        return False
    ipucu = f"{veri.get('name', '')} {veri.get('hint', '')} {veri.get('submit_name', '')}"
    return bool(veri.get("editable") or _RISKY_CLICK.search(ipucu) or _MESSAGE_FIELD.search(ipucu))


def key_needs_focus_lookup(key: str) -> bool:
    """Tuşun etkisi odaktaki alana bağlı mı (`describe_key` gerekir)."""
    base = _key_base(key) if key.strip() else "enter"
    return base in _ENTER_KEYS or base in _DELETE_KEYS


def _click_effect(result: dict[str, Any]) -> ToolEffect | None:
    """`describe` sonucundan tıklamanın etkisini çıkar; okunamazsa `None` (sorulur)."""
    veri = result.get("veri") if result.get("ok") else None
    if not isinstance(veri, dict):
        return None
    if chrome_guard.prohibited_reason(veri) is not None:
        # Araç çalışmayı reddeder (her kipte); sormanın anlamı yok (#422).
        return ToolEffect.REMOTE_INTERACT
    if chrome_guard.always_ask_reason(veri) is not None:
        # Yetki verme: İzinleri atla dahil her kipte sorulur (#422).
        return ToolEffect.REMOTE_DESTRUCTIVE
    ad = f"{veri.get('name', '')} {veri.get('type', '')}"
    if veri.get("link") and not veri.get("submit"):
        # Gerçek adrese giden bağlantı yalnız gezinir; iş yapan şey sonraki sayfadaki
        # düğmedir ve o ayrıca denetlenir. Tek istisna oturumu kapatmak.
        return None if _LOGOUT_LINK.search(ad) else ToolEffect.REMOTE_READ
    if veri.get("submit") or _RISKY_CLICK.search(ad):
        return None
    return ToolEffect.REMOTE_INTERACT


async def chrome_action(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tek araçta yardımcı sayfa işlemleri (Claude'daki gibi `action` alanıyla)."""
    action = require_str(args, "action")
    ref = args.get("ref")
    value = args.get("value")
    data: dict[str, Any] = {}
    if isinstance(ref, str) and ref:
        data["ref"] = ref
    if action == "scroll":
        # value: up|down|left|right, isteğe bağlı "down:600" (piksel).
        direction, _, amount = (value if isinstance(value, str) else "").partition(":")
        data["direction"] = direction if direction in {"up", "left", "right"} else "down"
        if amount.strip().isdigit():
            data["amount"] = int(amount)
        return await _call(context, "scroll", data)
    if action == "type_focused":
        if not isinstance(value, str) or not value:
            return ToolResult.failure("type_focused için 'value' alanına yazılacak metni yaz.")
        return await _call(context, "type", {"text": value})
    if action == "check":
        if "ref" not in data:
            return ToolResult.failure("check için 'ref' gerekli; value: true ya da false.")
        wanted = not (isinstance(value, str) and value.strip().lower() == "false")
        return await _call(context, "check", {**data, "value": wanted})
    if action == "resize":
        match = re.fullmatch(
            r"\s*(\d{3,4})\s*[x,]\s*(\d{3,4})\s*", value if isinstance(value, str) else ""
        )
        if match is None:
            return ToolResult.failure(
                "resize için 'value' alanına 'genişlik,yükseklik' yaz; ör. 1280,800."
            )
        return await _call(
            context, "resize", {"width": int(match.group(1)), "height": int(match.group(2))}
        )
    if action == "zoom":
        return await _zoom(value, context)
    if action == "wait":
        if not isinstance(value, str) or not value.strip():
            return ToolResult.failure(
                "wait için 'value' alanına beklenecek metni ya da 'network_idle' yaz."
            )
        if value.strip().lower() in NETWORK_IDLE_VALUES:
            return await _call(context, "wait", {"network_idle": True, "timeout_ms": 20_000})
        return await _call(context, "wait", {"text": value, "timeout_ms": 20_000})
    if action == "console":
        return await chrome_inspect.read_console(value, context, _call)
    if action == "network":
        return await chrome_inspect.read_network(value, context, _call)
    if action == "record":
        return await _record(value, context, args.get("filename"))
    if action == "shortcuts":
        return await _call(context, "shortcuts", {})
    if action == "shortcut":
        return await chrome_inspect.run_shortcut(value, context, _call)
    if action == "window":
        return await chrome_inspect.open_window(value, context, _call)
    if action == "group":
        return await chrome_inspect.group_tabs(value, context, _call)
    if action == "key":
        data["key"] = value if isinstance(value, str) and value else "Enter"
        if _key_base(data["key"]) in _ENTER_KEYS:
            ref_data = {"ref": data["ref"]} if "ref" in data else {}
            refused = await _prohibited(context, "describe_key", ref_data)
            if refused is not None:
                return refused
        return with_action_check(await _call(context, "key", data))
    if action == "screenshot":
        return await chrome_screenshot(args, context)
    if action == "tabs":
        if value == "create_if_empty":
            return await tabs_create_if_empty(context, _call)
        return await _call(context, "tabs", {})
    if action == "open":
        if not isinstance(value, str) or not value.strip():
            return ToolResult.failure("open için 'value' alanına adresi yaz.")
        url = value if value.startswith(("https://", "http://")) else f"https://{value}"
        reason = browser_block_reason(url, allowed_local(context))
        if reason is not None:
            return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
        return await _call(context, "tab_open", {"url": url})
    if action == "new_tab":
        # Claude `tabs_create_mcp`: oturum grubuna boş sekme (#431).
        return await _call(context, "tab_open", {"blank": True})
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
        if "ref" in data:
            return await _call(context, "hover", data)
        spot = _point(value, context)
        if spot is None:
            return ToolResult.failure("hover için 'ref' ya da 'value' alanına 'x,y' gerekli.")
        return await _call(context, "hover", {"x": spot[0], "y": spot[1]})
    if action == "text":
        page = int(value) if isinstance(value, str) and value.strip().isdigit() else 1
        return await _call(context, "text_page", {"page": max(1, page)})
    if action in {"click_at", *_CLICK_KINDS}:
        kind = _CLICK_KINDS.get(action)
        mods = parse_modifiers(args.get("modifiers"))
        if isinstance(mods, str):
            return ToolResult.failure(mods)
        extra: dict[str, Any] = {"kind": kind} if kind else {}
        if mods:
            extra["mods"] = mods
        if "ref" in data:
            refused = await _prohibited(context, "describe", {"ref": data["ref"]})
            if refused is not None:
                return refused
            return with_action_check(await _call(context, "click", {**data, **extra}))
        point = _point(value, context)
        if point is None:
            return ToolResult.failure(
                f"{action} için 'ref' ya da 'value' alanına ekran görüntüsündeki 'x,y' yaz."
            )
        refused = await _prohibited(context, "describe_at", {"x": point[0], "y": point[1]})
        if refused is not None:
            return refused
        return with_action_check(
            await _call(context, "click_at", {"x": point[0], "y": point[1], **extra})
        )
    if action == "drag":
        return await _drag(data, value, context, args.get("start"))
    if action == "wheel":
        delta = _delta(value)
        if delta is None:
            return ToolResult.failure("wheel için 'value' alanına 'dx,dy' (piksel) yaz; ör. 0,400.")
        return await _call(context, "wheel", {**data, "dx": delta[0], "dy": delta[1]})
    if action == "upload":
        return await _upload(data, value, context)
    if action == "upload_image":
        return await chrome_images.upload_image(dict(args), context, _call, _point)
    if action == "assets":
        return await chrome_assets(args, context)
    return ToolResult.failure(
        "action: scroll, wait, key, select, tabs, open, tab, screenshot, back, forward, "
        "reload, close, hover, text, click_at, double_click, right_click, triple_click, drag, "
        "wheel, type_focused, check, resize, zoom, upload, assets, console, network, record, "
        "shortcuts, shortcut, window ya da group olmalı."
    )


#: Tıklama türleri: `click_at`/ref ile birlikte eklentiye `kind` olarak gider.
_CLICK_KINDS = {"double_click": "double", "right_click": "right", "triple_click": "triple"}


async def _record(value: object, context: ToolContext, filename: object = None) -> ToolResult:
    """`record start|halt|stop|clear`: kareler eklentide toplanır, GIF `chrome_record` yazar.

    Claude `gif_creator`: halt = stop_recording (kareler tutulur), stop = export, clear.
    """
    op = value.strip().lower() if isinstance(value, str) else ""
    if op == "start":
        return await chrome_record.start_recording(context)
    if op == "halt":
        return await chrome_record.halt_recording(context)
    if op == "clear":
        return await chrome_record.clear_recording(context)
    if op == "stop":
        name = filename if isinstance(filename, str) else None
        return await chrome_record.stop_recording(context, name)
    return ToolResult.failure("record için 'value' alanına start, halt, stop ya da clear yaz.")


def _delta(value: object) -> tuple[float, float] | None:
    """'dx,dy' piksel; yalnız bir sayı verilirse dikey kaydırma sayılır."""
    if value is None or value == "":
        return 0.0, 400.0
    if not isinstance(value, str):
        return None
    parts = [p.strip() for p in value.split(",")]
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        return None
    if len(numbers) == 1:
        return 0.0, numbers[0]
    return (numbers[0], numbers[1]) if len(numbers) == 2 else None


async def _zoom(value: object, context: ToolContext) -> ToolResult:
    """Ekran görüntüsünün bir bölgesini (x1,y1,x2,y2 — görüntü pikseli) kırpıp büyütür."""
    match = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*", str(value or ""))
    if match is None:
        return ToolResult.failure("zoom için 'value' alanına 'x1,y1,x2,y2' (görüntü pikseli) yaz.")
    x1, y1, x2, y2 = (int(g) for g in match.groups())
    if x2 <= x1 or y2 <= y1:
        return ToolResult.failure("zoom bölgesi geçersiz: x2>x1 ve y2>y1 olmalı.")
    shot = await chrome_screenshot({}, context)
    if not shot.ok or not shot.content:
        return shot
    import io

    from PIL import Image

    raw = base64.b64decode(shot.content[0].data)
    with Image.open(io.BytesIO(raw)) as image:
        if x1 >= image.width or y1 >= image.height:
            return ToolResult.failure(
                f"zoom bölgesi görüntünün dışında: görüntü {image.width}x{image.height} piksel."
            )
        crop = image.crop((x1, y1, min(x2, image.width), min(y2, image.height)))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS).convert(
            "RGB"
        )
        out = io.BytesIO()
        crop.save(out, format="JPEG", quality=85)
    encoded = base64.b64encode(out.getvalue()).decode("ascii")
    return ToolResult(
        f"Ekran görüntüsünün {x1},{y1}-{x2},{y2} bölgesi (2x büyütüldü). Bu görüntü KIRPIKTIR: "
        "tıklamak için bu görüntüdeki değil, TAM ekran görüntüsündeki x,y koordinatını kullan "
        f"(kırpığın sol üstü tam görüntüde {x1},{y1}).",
        content=(ToolContent.image("image/jpeg", encoded),),
    )


async def _drag(
    data: dict[str, Any], value: object, context: ToolContext, start: object = None
) -> ToolResult:
    """Kaynak `ref` ya da `start` ('x,y') → hedef `value` (öğe ref'i ya da 'x,y')."""
    origin = None if "ref" in data else _point(start, context)
    if origin is not None:
        data = {"from_x": origin[0], "from_y": origin[1]}
    if ("ref" not in data and origin is None) or not isinstance(value, str) or not value.strip():
        return ToolResult.failure(
            "drag için 'ref' ya da 'start' (kaynak x,y) ve 'value' (hedef ref ya da x,y) gerekli."
        )
    if re.fullmatch(r"e\d+", value.strip()):
        return await _call(context, "drag", {**data, "to_ref": value.strip()})
    point = _point(value, context)
    if point is None:
        return ToolResult.failure("drag hedefi öğe ref'i (e12) ya da 'x,y' olmalı.")
    return await _call(context, "drag", {**data, "x": point[0], "y": point[1]})


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
    reason = browser_block_reason(url, allowed_local(context))
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    tab = args.get("tabId")
    extra = {"tabId": tab} if isinstance(tab, int) and not isinstance(tab, bool) else {}
    return await _call(context, "navigate", {"url": url, **extra})


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
        note += (
            f" Görüntü {size[0]}x{size[1]} px; tıklamak için computer left_click coordinate [x,y]."
        )
    image_id = chrome_images.remember(context.chrome, encoded)
    if image_id is not None:
        note += f" (imageId: {image_id}; upload_image ile yüklenebilir)"
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
    from .upload_guard import upload_refusal

    files: list[dict[str, str]] = []
    toplam = 0
    for raw in (part.strip() for part in value.split(",") if part.strip()):
        path = resolve_path(context, raw)
        if not path.is_file():
            return ToolResult.failure(f"Dosya yok: {raw}")
        refusal = upload_refusal(path, context)
        if refusal is not None:
            return ToolResult.failure(f"Yükleme reddedildi: {refusal}.")
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
