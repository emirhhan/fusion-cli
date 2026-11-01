"""Claude in Chrome çağrısını Fusion'ın iç Chrome aracına çevir (#431).

Model Claude'un araçlarını (`navigate`, `computer`, `form_input` …) Claude'un argüman
şemasıyla çağırır; çeviri aynı işi yapan iç `chrome_*` çağrısını verir. Onay, yasak eylem
denetimi (#422), yükleme kuralları (#437), plan kipi (#450) ve panel akışı iç adla
çalıştığı için güvenlik kuralları tek yerde kalır.

Dönüş: `(iç_ad, iç_argümanlar)`; argüman hatasında kullanıcıya/modele gidecek metin;
yerel işlenen çağrıda (`computer wait`, tarayıcı listesi) `None`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..core.claude_chrome_names import claude_chrome_short
from .chrome_claude_args import DEFAULT_MAX_CHARS, parse_modifiers

Legacy = tuple[str, dict[str, object]]
Translation = Legacy | str | None
Args = Mapping[str, object]

#: Bir kaydırma çentiğinin piksel karşılığı (Claude `scroll_amount` çentik sayar).
SCROLL_TICK_PX = 100
#: Varsayılan çentik sayısı (Claude belgesi: 3).
DEFAULT_SCROLL_TICKS = 3
#: Toplu çağrıdaki en fazla iç adım (`chrome_script.MAX_BATCH` ile aynı).
MAX_STEPS = 20

_CLICKS = {"right_click", "double_click", "triple_click"}


def _xy(value: object) -> str | None:
    if (
        isinstance(value, list | tuple)
        and len(value) == 2
        and all(isinstance(item, int | float) and not isinstance(item, bool) for item in value)
    ):
        return f"{value[0]},{value[1]}"
    return None


def _ref(args: Args) -> dict[str, object]:
    ref = args.get("ref")
    return {"ref": ref} if isinstance(ref, str) and ref else {}


def _act(action: str, **extra: object) -> Legacy:
    return "chrome_action", {"action": action, **{k: v for k, v in extra.items() if v}}


def _click(args: Args, action: str) -> Translation:
    mods = parse_modifiers(args.get("modifiers"))
    if isinstance(mods, str):
        return mods
    modifiers = "+".join(mods)
    ref = _ref(args)
    if action == "left_click" and ref and not modifiers:
        return "chrome_click", ref
    point = _xy(args.get("coordinate"))
    if not ref and point is None:
        return f"{action} için coordinate [x, y] ya da ref gerekli."
    inner = "click_at" if action == "left_click" else action
    return _act(inner, value=None if ref else point, modifiers=modifiers, **ref)


def _keys(args: Args) -> Translation:
    text = args.get("text")
    if not isinstance(text, str) or not text.split():
        return "key için text alanına tuş(lar)ı yaz; ör. 'Enter' ya da 'cmd+a'."
    repeat = args.get("repeat", 1)
    count = repeat if isinstance(repeat, int) and not isinstance(repeat, bool) else 1
    keys = text.split() * max(1, count)
    if len(keys) == 1:
        return _act("key", value=keys[0])
    if len(keys) > MAX_STEPS:
        return f"Tek çağrıda en çok {MAX_STEPS} tuş basılabilir."
    items = [{"name": "chrome_action", "input": {"action": "key", "value": k}} for k in keys]
    return "chrome_batch", {"actions": items}


def _scroll(args: Args) -> Translation:
    direction = args.get("scroll_direction")
    if direction not in {"up", "down", "left", "right"}:
        return "scroll için scroll_direction (up|down|left|right) gerekli."
    ticks = args.get("scroll_amount", DEFAULT_SCROLL_TICKS)
    ticks = ticks if isinstance(ticks, int | float) and ticks > 0 else DEFAULT_SCROLL_TICKS
    return _act("scroll", value=f"{direction}:{int(ticks * SCROLL_TICK_PX)}", **_ref(args))


def _drag(args: Args) -> Translation:
    target = _xy(args.get("coordinate"))
    start = _xy(args.get("start_coordinate"))
    ref = _ref(args)
    if target is None or (not ref and start is None):
        return "left_click_drag için start_coordinate (ya da kaynak ref) ve coordinate gerekli."
    return _act("drag", value=target, start=None if ref else start, **ref)


def _zoom(args: Args) -> Translation:
    region = args.get("region")
    if not (isinstance(region, list | tuple) and len(region) == 4):
        return "zoom için region [x0, y0, x1, y1] gerekli."
    return _act("zoom", value=",".join(str(item) for item in region))


def _computer(args: Args) -> Translation:
    action = args.get("action")
    if action == "left_click" or action in _CLICKS:
        return _click(args, str(action))
    if action == "type":
        text = args.get("text")
        if not isinstance(text, str) or not text:
            return "type için text gerekli."
        return _act("type_focused", value=text)
    simple: dict[object, Callable[[Args], Translation]] = {
        "screenshot": lambda _a: _act("screenshot"),
        "key": _keys,
        "scroll": _scroll,
        "left_click_drag": _drag,
        "zoom": _zoom,
    }
    if action in simple:
        return simple[action](args)
    if action in {"hover", "scroll_to"}:
        ref = _ref(args)
        point = _xy(args.get("coordinate"))
        if action == "hover" and not ref and point is not None:
            return _act("hover", value=point)
        if not ref:
            return f"{action} Fusion'da öğe ref'i ister (read_page/find)."
        # scroll_to öğeyi görünüme kaydırır; fare olayı (hover) göndermez.
        return _act("hover" if action == "hover" else "scroll", **ref)
    if action == "wait":
        return None
    return f"computer action tanınmadı: {action!r}."


def _navigate(args: Args) -> Translation:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return "navigate için url gerekli."
    if url.strip().lower() in {"back", "forward"}:
        return _act(url.strip().lower())
    tab = args.get("tabId")
    extra = {"tabId": tab} if isinstance(tab, int) and not isinstance(tab, bool) else {}
    return "chrome_navigate", {"url": url.strip(), **extra}


def _read_page(args: Args) -> Translation:
    data: dict[str, object] = {
        "tree": "interactive" if args.get("filter") == "interactive" else "all"
    }
    if isinstance(args.get("depth"), int):
        data["depth"] = args["depth"]
    if isinstance(args.get("ref_id"), str) and args["ref_id"]:
        data["ref"] = args["ref_id"]
    limit = args.get("max_chars")
    if not isinstance(limit, int | float) or isinstance(limit, bool) or limit <= 0:
        limit = DEFAULT_MAX_CHARS  # Claude: "limited to 50000 characters by default".
    data["max_chars"] = int(limit)
    return "chrome_page", data


def _find(args: Args) -> Translation:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return "find için query gerekli."
    return "chrome_page", {"query": query}


def _form_input(args: Args) -> Translation:
    ref = _ref(args)
    value = args.get("value")
    if not ref or value is None:
        return "form_input için ref ve value gerekli."
    if isinstance(value, bool):
        return _act("check", value="true" if value else "false", **ref)
    return "chrome_type", {**ref, "text": str(value)}


def _console(args: Args) -> Translation:
    pattern = args.get("pattern") if isinstance(args.get("pattern"), str) else ""
    if args.get("onlyErrors") is True:
        return _act("console", value=f"errors:{pattern}" if pattern else "errors")
    return _act("console", value=pattern)


def _gif(args: Args) -> Translation:
    action = args.get("action")
    if action == "start_recording":
        return _act("record", value="start")
    if action == "stop_recording":
        # Claude gibi: kare almayı durdurur, kareler export/clear'e dek tutulur.
        return _act("record", value="halt")
    if action == "export":
        name = args.get("filename")
        return _act("record", value="stop", filename=name if isinstance(name, str) else None)
    if action == "clear":
        return _act("record", value="clear")
    return "gif_creator action: start_recording, stop_recording, export ya da clear."


def _shortcut(args: Args) -> Translation:
    name = args.get("command") or args.get("shortcutId")
    if not isinstance(name, str) or not name.strip():
        return "shortcuts_execute için command ya da shortcutId gerekli."
    return _act("shortcut", value=name.strip().lstrip("/"))


def _close(args: Args) -> Translation:
    tab = args.get("tabId")
    if not isinstance(tab, int) or isinstance(tab, bool):
        return "tabs_close_mcp için tabId gerekli."
    return _act("close", value=str(tab))


def _javascript(args: Args) -> Translation:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        return "javascript_tool için text gerekli."
    return "chrome_javascript", {"text": text}


def _upload(args: Args) -> Translation:
    paths = args.get("paths")
    ref = _ref(args)
    if not ref or not isinstance(paths, list) or not paths:
        return "file_upload için ref ve paths gerekli."
    if not all(isinstance(path, str) and path and "," not in path for path in paths):
        return "file_upload paths: virgül içermeyen dosya yolları listesi olmalı."
    return _act("upload", value=",".join(paths), **ref)


def _upload_image(args: Args) -> Translation:
    image_id = args.get("imageId")
    if not isinstance(image_id, str) or not image_id.strip():
        return "upload_image için imageId gerekli (screenshot çıktısındaki kimlik)."
    ref, point = _ref(args), _xy(args.get("coordinate"))
    if bool(ref) == (point is not None):
        return "upload_image için ref ya da coordinate'ten yalnız birini ver."
    name = args.get("filename")
    return _act(
        "upload_image",
        value=image_id.strip(),
        point=point,
        filename=name if isinstance(name, str) else None,
        **ref,
    )


def _resize(args: Args) -> Translation:
    width, height = args.get("width"), args.get("height")
    if not isinstance(width, int | float) or not isinstance(height, int | float):
        return "resize_window için width ve height gerekli."
    return _act("resize", value=f"{int(width)},{int(height)}")


_TRANSLATORS: dict[str, Callable[[Args], Translation]] = {
    "navigate": _navigate,
    "read_page": _read_page,
    "find": _find,
    "form_input": _form_input,
    "computer": _computer,
    "get_page_text": lambda _a: _act("text"),
    "read_console_messages": _console,
    "read_network_requests": lambda a: _act(
        "network", value=a.get("urlPattern") if isinstance(a.get("urlPattern"), str) else None
    ),
    "gif_creator": _gif,
    "shortcuts_list": lambda _a: _act("shortcuts"),
    "shortcuts_execute": _shortcut,
    "tabs_context_mcp": lambda a: _act(
        "tabs", value="create_if_empty" if a.get("createIfEmpty") is True else None
    ),
    "tabs_create_mcp": lambda _a: _act("new_tab"),
    "tabs_close_mcp": _close,
    "javascript_tool": _javascript,
    "file_upload": _upload,
    "upload_image": _upload_image,
    "resize_window": _resize,
}

#: `tabId`'yi kendisi işleyen ya da sekmeye bağlı olmayan araçlar (önceden sekme seçilmez).
NO_TAB_SELECT = frozenset({"navigate", "tabs_close_mcp", "tabs_context_mcp", "tabs_create_mcp"})


def translate(name: str, args: Args) -> Translation:
    """Claude adlı çağrıyı iç çağrıya çevir; Claude aracı değilse `None` döner."""
    short = claude_chrome_short(name)
    if short is None:
        return None
    if short == "browser_batch":
        return translate_batch(args)
    translator = _TRANSLATORS.get(short)
    return None if translator is None else translator(args)


def requested_tab(name: str, args: Args) -> int | None:
    """Çalışmadan önce seçilecek sekme (`tabId`); gerekmiyorsa `None`."""
    short = claude_chrome_short(name)
    tab = args.get("tabId")
    if short is None or short in NO_TAB_SELECT or short == "browser_batch":
        return None
    return tab if isinstance(tab, int) and not isinstance(tab, bool) and tab > 0 else None


def translate_batch(args: Args) -> Translation:
    """`browser_batch` öğelerini (Claude kısa adları da olur) iç `chrome_batch`'e çevir.

    Öğenin `tabId`'si önceki öğeden farklıysa araya sekme seçimi eklenir; iç ad
    (`chrome_action` …) olduğu gibi geçer.
    """
    raw = args.get("actions")
    if not isinstance(raw, list) or not raw:
        return "actions boş: [{name, input}] listesi ver."
    steps: list[dict[str, object]] = []
    current: int | None = None
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping) or not isinstance(item.get("input", {}), Mapping):
            return f"{index}. öğe {{name, input}} nesnesi olmalı."
        name, data = str(item.get("name", "")), dict(item.get("input", {}))
        short = claude_chrome_short(name)
        if short is None:
            steps.append({"name": name, "input": data})
            continue
        if short == "browser_batch":
            return f"{index}. öğe: toplu çağrı iç içe olamaz."
        tab = requested_tab(name, data)
        if tab is not None and tab != current:
            steps.append({"name": "chrome_action", "input": {"action": "tab", "value": str(tab)}})
            current = tab
        inner = translate(name, data)
        if inner is None:
            return f"{index}. öğe: '{name}' toplu çağrıda kullanılamaz."
        if isinstance(inner, str):
            return f"{index}. öğe: {inner}"
        if inner[0] == "chrome_batch":
            steps.extend(inner[1]["actions"])  # type: ignore[arg-type]
        else:
            steps.append({"name": inner[0], "input": inner[1]})
    if len(steps) > MAX_STEPS:
        return f"Tek toplu çağrıda en çok {MAX_STEPS} eylem olabilir."
    return "chrome_batch", {"actions": steps}
