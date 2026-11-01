"""Claude in Chrome araç seti (#431, #432): Claude'un adları ve argüman şemaları.

Model `claude-in-chrome__navigate`, `…__computer` gibi araçları görür (Claude Code'da
`mcp__claude-in-chrome__*`; izin kuralı ve kanca bu adla eşleşir). Ajan döngüsü çağrıyı
onaydan önce iç `chrome_*` çağrısına çevirir (`claude_chrome_translate`); burada tanımlı
çalıştırıcı, döngü dışından (doğrudan kayıt defteri) gelen çağrıyı aynı çeviriyle yürütür.
Eski `chrome_*` adları gizli kalır ve çalışmaya devam eder.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable

from ..core.claude_chrome_names import (
    CLAUDE_CHROME_READ,
    claude_chrome_name,
    claude_chrome_short,
)
from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from .claude_chrome_translate import requested_tab, translate

SchemaFragment = dict[str, object]

_S: SchemaFragment = {"type": "string"}
_N: SchemaFragment = {"type": "number"}
_B: SchemaFragment = {"type": "boolean"}
_XY: SchemaFragment = {"type": "array", "items": _N}
_TAB = {"tabId": _N}
#: `computer wait` üst sınırı (Claude: en çok 10 sn).
MAX_WAIT_S = 10.0
#: Kimlik göndermeyen eklentinin (ya da çoklu cihaz bilmeyen köprünün) `deviceId`'si.
LOCAL_DEVICE_ID = "fusion-local"
#: `switch_browser`: kullanıcının başka tarayıcıda "Bu tarayıcıyı kullan"a basması için süre.
SWITCH_WAIT_S = 60.0

_COMPUTER_ACTIONS = [
    "left_click", "right_click", "type", "screenshot", "wait", "scroll", "key",
    "left_click_drag", "double_click", "triple_click", "zoom", "scroll_to", "hover",
]  # fmt: skip


def _obj(props: dict[str, SchemaFragment], required: list[str] | None = None) -> SchemaFragment:
    return {"type": "object", "properties": props, "required": required or []}


_SPECS: dict[str, tuple[str, SchemaFragment]] = {
    "navigate": (
        "URL'ye git; url=back|forward.",
        _obj({"url": _S, **_TAB}, ["url"]),
    ),
    "read_page": (
        "Erişilebilirlik ağacı (ref'li).",
        _obj(
            {
                "filter": {**_S, "enum": ["interactive", "all"]},
                "depth": _N,
                "ref_id": _S,
                "max_chars": _N,
                **_TAB,
            }
        ),
    ),
    "find": (
        "Öğeyi doğal dille bul; ref döner.",
        _obj({"query": _S, **_TAB}, ["query"]),
    ),
    "form_input": (
        "Alana değer ver (onay kutusu: boolean).",
        _obj({"ref": _S, "value": {}, **_TAB}, ["ref", "value"]),
    ),
    "computer": (
        "Fare/klavye/ekran görüntüsü; ref ya da coordinate [x,y].",
        _obj(
            {
                "action": {**_S, "enum": _COMPUTER_ACTIONS},
                "coordinate": _XY,
                "ref": _S,
                "text": _S,
                "duration": _N,
                "scroll_direction": {**_S, "enum": ["up", "down", "left", "right"]},
                "scroll_amount": _N,
                "start_coordinate": _XY,
                "region": {"type": "array", "items": _N},
                "modifiers": _S,
                "repeat": _N,
                **_TAB,
            },
            ["action"],
        ),
    ),
    "get_page_text": ("Sayfanın düz metni.", _obj(dict(_TAB))),
    "tabs_context_mcp": ("Gruptaki sekmeler (tabId).", _obj({"createIfEmpty": _B})),
    "tabs_create_mcp": ("Gruba boş sekme aç.", _obj({})),
    "tabs_close_mcp": ("Sekmeyi kapat.", _obj(dict(_TAB), ["tabId"])),
    "read_console_messages": (
        "Konsol iletileri.",
        _obj({"pattern": _S, "onlyErrors": _B, "limit": _N, "clear": _B, **_TAB}),
    ),
    "read_network_requests": (
        "Ağ istekleri.",
        _obj({"urlPattern": _S, "limit": _N, "clear": _B, **_TAB}),
    ),
    "gif_creator": (
        "Ekran kaydı (GIF).",
        _obj(
            {
                "action": {**_S, "enum": ["start_recording", "stop_recording", "export", "clear"]},
                "download": _B,
                "filename": _S,
                **_TAB,
            },
            ["action"],
        ),
    ),
    "shortcuts_list": ("Kayıtlı kısayollar.", _obj(dict(_TAB))),
    "shortcuts_execute": ("Kısayolu çalıştır.", _obj({"command": _S, "shortcutId": _S, **_TAB})),
    "javascript_tool": (
        "Sayfada JavaScript çalıştır; son ifadenin değeri döner (her seferinde sorulur).",
        _obj({"action": {**_S, "enum": ["javascript_exec"]}, "text": _S, **_TAB}, ["text"]),
    ),
    "file_upload": (
        "Dosya alanına dosya yükle.",
        _obj({"paths": {"type": "array", "items": _S}, "ref": _S, **_TAB}, ["ref", "paths"]),
    ),
    "upload_image": (
        "Ekran görüntüsünü (imageId) dosya alanına ya da bırakma noktasına yükle.",
        _obj({"imageId": _S, "ref": _S, "coordinate": _XY, "filename": _S, **_TAB}, ["imageId"]),
    ),
    "resize_window": (
        "Pencereyi boyutlandır.",
        _obj({"width": _N, "height": _N, **_TAB}, ["width", "height"]),
    ),
    "browser_batch": (
        "Tarayıcı araçlarını sırayla çalıştır; ilk hatada durur. actions=[{name, input}].",
        _obj({"actions": {"type": "array", "items": {"type": "object"}}}, ["actions"]),
    ),
    "list_connected_browsers": ("Bağlı Chrome tarayıcıları.", _obj({})),
    "select_browser": ("Tarayıcıyı deviceId ile seç.", _obj({"deviceId": _S}, ["deviceId"])),
    "switch_browser": ("Başka tarayıcıya bağlan.", _obj({})),
}


def _legacy_tool(name: str) -> Tool | None:
    from .chrome_script import batch_tool

    return batch_tool(name)


async def select_requested_tab(
    name: str, args: ToolArgs, context: ToolContext
) -> ToolResult | None:
    """`tabId` verilmişse işlemden ÖNCE o sekmeyi bağla; hata varsa sonucu döner.

    Önbellek yok: kullanıcı sekmeyi elle değiştirmiş olabilir; eski kayıtla yanlış sekmede
    tıklamak, her çağrıda bir seçim gidiş-dönüşünden pahalıdır.
    """
    tab = requested_tab(name, args)
    if tab is None or context.chrome is None:
        return None
    from .chrome import _call

    result = await _call(context, "tab_select", {"id": tab})
    if result.ok:
        return None
    return ToolResult.failure(
        f"Sekme {tab} seçilemedi: {result.output}. Boş sekmeyse önce navigate ile bir adrese git."
    )


async def _local(short: str, args: ToolArgs, context: ToolContext) -> ToolResult:
    if short == "computer":
        duration = args.get("duration", 1)
        seconds = float(duration) if isinstance(duration, int | float) else 1.0
        await asyncio.sleep(max(0.0, min(seconds, MAX_WAIT_S)))
        return ToolResult(f"{seconds:g} sn beklendi.")
    if short in ("list_connected_browsers", "select_browser", "switch_browser"):
        return await _browser_choice(short, args, context)
    return ToolResult.failure(f"{short} çevrilemedi.")


def _browsers(chrome: object) -> list[dict[str, object]]:
    lister = getattr(chrome, "browsers", None)
    if callable(lister):
        return list(lister())
    return [{"deviceId": LOCAL_DEVICE_ID, "name": "Chrome", "isLocal": True, "inUse": True}]


async def _browser_choice(short: str, args: ToolArgs, context: ToolContext) -> ToolResult:
    """#432: bağlı tarayıcıları listele, seç ya da kullanıcıdan başka tarayıcı seçmesini iste."""
    chrome = context.chrome
    if short == "list_connected_browsers":
        browsers = _browsers(chrome) if chrome is not None else []
        return ToolResult(json.dumps(browsers, ensure_ascii=False))
    if chrome is None:
        return ToolResult.failure("Bağlı Chrome yok; /chrome ile bağlan.")
    if short == "select_browser":
        device_id = args.get("deviceId")
        selector = getattr(chrome, "select_browser", None)
        if not callable(selector):
            if device_id == LOCAL_DEVICE_ID:
                return ToolResult(f"{LOCAL_DEVICE_ID} seçildi.")
            return ToolResult.failure(f"Bilinmeyen deviceId; bağlı tek tarayıcı: {LOCAL_DEVICE_ID}.")
        chosen = selector(device_id) if isinstance(device_id, str) else None
        if chosen is None:
            ids = ", ".join(str(b["deviceId"]) for b in _browsers(chrome)) or "yok"
            return ToolResult.failure(f"Bu deviceId bağlı değil. Bağlı tarayıcılar: {ids}.")
        return ToolResult(f"{chosen['name']} ({chosen['deviceId']}) seçildi.")
    switcher = getattr(chrome, "request_switch", None)
    if not callable(switcher):
        return ToolResult.failure("Bu köprü başka tarayıcıya geçişi desteklemiyor.")
    chosen = await switcher(SWITCH_WAIT_S)
    if chosen is None:
        return ToolResult.failure(
            "Hiçbir tarayıcıda 'Bu tarayıcıyı kullan' seçilmedi. Kullanmak istediğin tarayıcıda "
            "Fusion yan panelini açıp seçimi yap ya da terminalde /chrome select çalıştır."
        )
    return ToolResult(f"{chosen['name']} ({chosen['deviceId']}) seçildi.")


def _runner(short: str) -> Callable[[ToolArgs, ToolContext], Awaitable[ToolResult]]:
    async def run(args: ToolArgs, context: ToolContext) -> ToolResult:
        translated = translate(claude_chrome_name(short), args)
        if isinstance(translated, str):
            return ToolResult.failure(translated)
        if translated is None:
            return await _local(short, args, context)
        refused = await select_requested_tab(claude_chrome_name(short), args, context)
        if refused is not None:
            return refused
        tool = _legacy_tool(translated[0])
        if tool is None:
            return ToolResult.failure(f"İç Chrome aracı yok: {translated[0]}")
        outcome = tool.run(translated[1], context)
        return await outcome if inspect.isawaitable(outcome) else outcome

    return run


def _effect(
    short: str,
) -> Callable[[ToolArgs, ToolContext | None], Awaitable[ToolEffect | None]]:
    async def resolve(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
        translated = translate(claude_chrome_name(short), args)
        if not isinstance(translated, tuple):
            return ToolEffect.REMOTE_READ
        tool = _legacy_tool(translated[0])
        if tool is None:
            return None
        if tool.effect_resolver is None:
            return tool.effect if tool.mutating else ToolEffect.REMOTE_READ
        outcome = tool.effect_resolver(translated[1], context)
        return await outcome if inspect.isawaitable(outcome) else outcome

    return resolve


def claude_chrome_tools() -> tuple[Tool, ...]:
    """Claude adlı araçlar; okuyanlar değiştirici değildir."""
    tools: list[Tool] = []
    for short, (description, schema) in _SPECS.items():
        reads = short in CLAUDE_CHROME_READ
        tools.append(
            Tool(
                name=claude_chrome_name(short),
                description=description,
                parameters=schema,
                run=_runner(short),
                mutating=not reads,
                effect=ToolEffect.REMOTE_DESTRUCTIVE
                if short == "javascript_tool"
                else ToolEffect.REMOTE_WRITE,
                effect_resolver=None if reads else _effect(short),
            )
        )
    return tuple(tools)


def legacy_view(name: str, args: ToolArgs) -> tuple[str, ToolArgs]:
    """Arayüz metni için iç ad/argüman (panel akışı ve ilerleme satırı `chrome_*` okur)."""
    if claude_chrome_short(name) is None:
        return name, args
    translated = translate(name, args)
    return translated if isinstance(translated, tuple) else (name, args)
