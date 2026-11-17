"""Masaüstü eylem politikası: hedef uygulama, kademe tablosu ve engeller (P-007).

Claude Desktop computer use uygulama başına çalışır: ilk kullanımda "Allow for this session /
Deny" sorar, erişim kademesi kategoriye göre SABİTTİR ve değiştirilemez ("These tiers are fixed
by app category and can't be changed", #424): tarayıcılar ve yatırım platformları = View only,
terminal/IDE = Click only, diğer her şey = Full control (#425; engelli kategori yok). Terminal /
Finder / System Settings ek uyarı taşır. Kullanıcı yalnız reddedilen uygulamalar listesi tutar.
Bu modül aynı kararı Fusion'ın araçları için verir:

1. Eylemin HEDEF uygulamasını çöz: tıklama noktasındaki pencerenin sahibi (AX), klavyede
   öndeki uygulama, arka plan araçlarında `pid`, `desktop_open`'da verilen ad.
2. Uygulamanın kademesini bul: ret listesi → Fusion'ın kendisi → sabit kategori tablosu.
   Kullanımdan kalkan `desktop.app_levels`, `control_level`, `category_defaults` okunur ama
   uygulanmaz (yükleyici bir kez uyarır).
3. Eylemin istediği kademeyle karşılaştır; yetmiyorsa ya da uygulama engelliyse çağrı
   sorulmadan kapanır (her kipte, `bypass` dahil). Oturum onayı ve riskli eylem kararı
   onay katmanındadır (`engines/agent/desktop_approval.py`).

Ölçüldü (31 Ekim): onay yalnız aracın etkisine göreydi (otomatik kipte her `desktop_click`
sorulur, bypass'ta hiç); hedef uygulama kavramı, oturum hatırlama ve kategori/engel listesi
yoktu: model Fusion'ın kendi onay kartına bile tıklayabilirdi.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from ..core.desktop_settings import DesktopLevel, DesktopSettings, DesktopTarget
from ..core.tools import ToolArgs, ToolContext, ToolEffect
from .args import coerce_int
from .desktop_risk import UNVERIFIED_ELEMENT, risky_reason
from .native_desktop import SwiftDesktop

#: Hedef sorgusu: yardımcıya giden istek gövdesi → yanıt (testte sahte verilir).
TargetProbe = Callable[[dict[str, object]], Awaitable[Mapping[str, object]]]

BROWSER_HINT = "Web işi için chrome_* ya da browser_* araçlarını kullan."
SHELL_HINT = "Kabuk erişimine eşdeğer: komut için run_shell kullan."
LEVEL_SETTING_HINT = (
    "Kademeler uygulama kategorisine göre sabittir; bu eylemi başka bir yoldan yap."
)
DENIED_REASON = "{app} reddedilen uygulamalar listesinde (desktop.denied_apps)"
FUSION_REASON = "Fusion kendi penceresini yönetemez (kendi onay kartını onaylayamaz)"
LEVEL_REASON = "{app} için kademe '{level}', bu eylem '{required}' ister. {hint}"
#: Arka plan aracının hedefi (pid) doğrulanamadı: ret listesi denetlenemez, çağrı kapanır.
UNVERIFIED_REASON = (
    "hedef uygulama doğrulanamadı (geçerli window_id ve pid gerekli; pencere kapanmış olabilir)"
)


@dataclass(frozen=True, slots=True)
class AppCategory:
    """Kategori tablosunun bir satırı; `level` None ise uygulama engellidir."""

    key: str
    label: str
    level: DesktopLevel | None
    warning: str
    #: Paket kimliği önekleri (küçük harf).
    bundles: tuple[str, ...]
    #: Uygulama adları (küçük harf); ad bununla başlıyorsa da eşleşir ("Visual Studio Code -").
    names: tuple[str, ...]
    #: Yalnız tam ad eşleşsin (önek değil). Ölçüldü (31 Ekim): Fusion'ın "fusion " öneki
    #: "Fusion 360", "Fusion Studio" gibi ilgisiz uygulamaları kalıcı engelliyordu.
    exact_names: bool = False

    def matches(self, app: str, bundle: str) -> bool:
        name, ident = normalize_app(app), normalize_app(bundle)
        if ident and any(ident.startswith(prefix) for prefix in self.bundles):
            return True
        return bool(name) and any(
            name == item or (not self.exact_names and name.startswith(item + " "))
            for item in self.names
        )


def normalize_app(name: str) -> str:
    """Karşılaştırma anahtarı: biçim karakterleri atılır, küçük harf.

    Ölçüldü (31 Ekim): WhatsApp'ın adı '\u200eWhatsApp' geliyor; ad eşleşmesi tutmuyordu.
    """
    return "".join(char for char in name if unicodedata.category(char) != "Cf").strip().casefold()


#: Sıralıdır: ilk eşleşen kazanır (Fusion ve engelliler önce).
CATEGORIES: tuple[AppCategory, ...] = (
    AppCategory(
        "fusion", "Fusion", None, FUSION_REASON, ("com.fusion.desktop", "fusion.exe"), ("fusion",),
        exact_names=True,
    ),
    AppCategory(
        "finance", "yatırım platformu", DesktopLevel.OBSERVE,
        "Yatırım platformu: yalnız ekran görüntüsünde görülebilir.",
        ("com.binance", "com.coinbase", "com.krakenfx", "net.metaquotes", "com.tradingview",
         "com.robinhood", "com.interactivebrokers", "com.ledger", "com.exodus", "io.trezor",
         "org.electrum", "com.etoro", "com.webull", "com.tdameritrade",
         # Windows exe adları (#430): MetaTrader 4/5, TradingView, IBKR TWS, Ledger…
         "terminal.exe", "terminal64.exe", "tradingview.exe", "tws.exe", "ledger live.exe",
         "exodus.exe", "binance.exe", "thinkorswim.exe", "webull desktop.exe"),
        ("binance", "coinbase", "kraken", "metatrader 4", "metatrader 5", "tradingview",
         "robinhood", "trader workstation", "ibkr desktop", "thinkorswim", "ledger live",
         "exodus", "trezor suite", "electrum", "etoro", "webull", "midas", "btcturk", "paribu",
         "matriks", "bitlo", "icrypex"),
    ),
    AppCategory(
        "browser", "tarayıcı", DesktopLevel.OBSERVE, BROWSER_HINT,
        ("com.apple.safari", "com.google.chrome", "org.mozilla.firefox", "com.microsoft.edgemac",
         "com.brave.browser", "company.thebrowser.browser", "com.operasoftware.opera",
         "com.vivaldi.vivaldi", "ru.yandex.desktop.yandex-browser", "org.chromium.chromium",
         "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
         "arc.exe", "chromium.exe", "browser.exe", "iexplore.exe"),
        ("safari", "google chrome", "firefox", "microsoft edge", "brave browser", "arc", "opera",
         "vivaldi", "chromium", "yandex"),
    ),
    AppCategory(
        "terminal", "terminal", DesktopLevel.CLICK, SHELL_HINT,
        ("com.apple.terminal", "com.googlecode.iterm2", "dev.warp.warp", "net.kovidgoyal.kitty",
         "com.github.wez.wezterm", "io.alacritty", "org.alacritty", "com.mitchellh.ghostty",
         "windowsterminal.exe", "openconsole.exe", "conhost.exe", "cmd.exe", "powershell.exe",
         "pwsh.exe", "wezterm-gui.exe", "alacritty.exe", "mintty.exe", "wsl.exe", "bash.exe"),
        ("terminal", "iterm", "iterm2", "warp", "kitty", "wezterm", "alacritty", "ghostty"),
    ),
    AppCategory(
        "ide", "IDE", DesktopLevel.CLICK, SHELL_HINT,
        ("com.microsoft.vscode", "com.todesktop.230313mzl4w4u92", "com.jetbrains.",
         "com.apple.dt.xcode", "dev.zed.zed", "com.sublimetext.", "com.exafunction.windsurf",
         "com.google.android.studio",
         "code.exe", "cursor.exe", "devenv.exe", "windsurf.exe", "zed.exe", "sublime_text.exe",
         "idea64.exe", "pycharm64.exe", "webstorm64.exe", "goland64.exe", "phpstorm64.exe",
         "rider64.exe", "clion64.exe", "studio64.exe"),
        ("visual studio code", "code", "cursor", "xcode", "zed", "sublime text", "windsurf",
         "intellij idea", "pycharm", "webstorm", "android studio", "goland", "phpstorm"),
    ),
    AppCategory(
        "chat", "sohbet", DesktopLevel.FULL,
        "Enter mesajı gönderir; her gönderim ayrıca sorulur (Shift+Enter satır ekler).",
        ("com.tinyspeck.slackmacgap", "com.apple.mobilesms", "net.whatsapp.whatsapp",
         "desktop.whatsapp", "ru.keepcoder.telegram", "org.telegram.desktop", "com.hnc.discord",
         "com.microsoft.teams", "org.whispersystems.signal-desktop", "com.facebook.archon",
         "slack.exe", "whatsapp.exe", "telegram.exe", "discord.exe", "ms-teams.exe",
         "teams.exe", "signal.exe", "messenger.exe"),
        ("slack", "messages", "mesajlar", "whatsapp", "telegram", "discord", "microsoft teams",
         "signal", "messenger"),
    ),
    AppCategory(
        "system", "Sistem Ayarları", DesktopLevel.FULL,
        "Sistem ayarlarını değiştirebilir; her eylem ayrıca sorulur.",
        ("com.apple.systempreferences", "com.apple.settings", "systemsettings.exe", "control.exe",
         "regedit.exe", "mmc.exe", "taskmgr.exe"),
        ("system settings", "system preferences", "sistem ayarları", "sistem tercihleri",
         "settings", "ayarlar", "control panel", "denetim masası"),
    ),
    AppCategory(
        "finder", "Finder", DesktopLevel.FULL, "Her dosyayı okuyup yazabilir.",
        ("com.apple.finder", "explorer.exe"), ("finder", "file explorer", "dosya gezgini"),
    ),
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class DesktopAssessment:
    """Bir masaüstü çağrısının politika kararı (onay katmanının girdisi)."""

    #: Eylemin istediği kademe.
    required: DesktopLevel
    #: Çözülen hedef; çözülemediyse None (çağrı her kipte, her seferinde sorulur).
    target: DesktopTarget | None = None
    #: Sorulmadan kapanma gerekçesi (ret listesi, engelli kategori, yetmeyen kademe).
    blocked: str | None = None
    #: Riskli eylem gerekçesi (gönder/sil/öde, Terminal'de Enter; P-008): her seferinde sorulur.
    risky: str | None = None


def category_for(app: str, bundle: str) -> AppCategory | None:
    return next((item for item in CATEGORIES if item.matches(app, bundle)), None)


def _app_keys(app: str, bundle: str) -> frozenset[str]:
    return frozenset(item for item in (normalize_app(app), normalize_app(bundle)) if item)


def app_level(
    settings: DesktopSettings, app: str, bundle: str = ""
) -> tuple[DesktopLevel | None, AppCategory | None, str]:
    """Uygulamanın kademesi (None = engelli), kategorisi ve engel gerekçesi.

    Kademe yalnız sabit kategori tablosundan gelir (#424); ret listesi ve Fusion'ın kendi
    penceresi dışında engelli uygulama yoktur (#425).
    """
    keys = _app_keys(app, bundle)
    category = category_for(app, bundle)
    if any(normalize_app(item) in keys for item in settings.denied_apps):
        return None, category, DENIED_REASON.format(app=app or bundle)
    if category is not None and category.key == "fusion":
        return None, category, FUSION_REASON
    if category is None or category.level is None:
        return DesktopLevel.FULL, category, ""
    return category.level, category, ""


#: Kademe gerektiren araçlar; listede olmayan masaüstü aracı (tam ekran görüntüsü, listeler)
#: belirli bir uygulamaya dokunmaz.
_TOOL_LEVELS = {
    "desktop_click": DesktopLevel.CLICK,
    "desktop_scroll": DesktopLevel.CLICK,
    "desktop_type": DesktopLevel.FULL,
    "desktop_key": DesktopLevel.FULL,
    "desktop_open": DesktopLevel.OBSERVE,
    "desktop_window_focus": DesktopLevel.OBSERVE,
    "desktop_background_screenshot": DesktopLevel.OBSERVE,
    "desktop_background_inspect": DesktopLevel.OBSERVE,
}
#: Claude "Full control" = tıkla, yaz, sürükle, kısayol: sürükleme ve basılı tutma tam kademedir.
_FULL_MOUSE_ACTIONS = frozenset({"drag", "down", "up"})
_POINT_TOOLS = frozenset({"desktop_mouse", "desktop_click", "desktop_scroll"})
_NAMED_TOOLS = frozenset({"desktop_open", "desktop_window_focus"})
_INTERACTIVE_TOOLS = _POINT_TOOLS | {"desktop_type", "desktop_key"}


def required_level(tool_name: str, args: ToolArgs) -> DesktopLevel | None:
    """Eylemin istediği kademe; belirli bir uygulamaya dokunmuyorsa None."""
    if tool_name == "desktop_mouse":
        action = args.get("action", "click")
        return DesktopLevel.FULL if action in _FULL_MOUSE_ACTIONS else DesktopLevel.CLICK
    if tool_name == "desktop_background_action":
        return DesktopLevel.FULL if args.get("action") == "set_value" else DesktopLevel.CLICK
    return _TOOL_LEVELS.get(tool_name)


async def _swift_probe(request: dict[str, object]) -> Mapping[str, object]:
    from . import desktop_win32

    if desktop_win32.active():
        # Windows (#430): WindowFromPoint / öndeki pencere → süreç → exe; UIA ile öğe adı.
        import asyncio

        from .desktop_win32_screen import probe

        try:
            return await asyncio.to_thread(probe, request)
        except OSError as exc:
            return {"ok": False, "metin": str(exc)}
    return await SwiftDesktop().invoke("target", {"kind": "probe", "request": request})


def background_pid(args: ToolArgs) -> int | None:
    """Arka plan aracının pid'i, aracın kendi kuralıyla (`desktop_background._target`).

    Ölçüldü (31 Ekim): politika yalnız `type(pid) is int` kabul ediyordu; araç ise "1234" ve
    1234.0'ı da çözer. Metin pid'de politika ÖNDEKİ uygulamayı değerlendiriyor, eylem başka
    sürece (ör. ret listesindeki parola yöneticisine) gidiyordu.
    """
    window, pid = coerce_int(args.get("window_id")), coerce_int(args.get("pid"))
    if window is None or pid is None or window <= 0 or pid <= 0:
        return None
    return pid


def _probe_request(tool_name: str, args: ToolArgs, context: ToolContext) -> dict[str, object]:
    """Yardımcıya sorulacak hedef: nokta (son görüntünün pikseli → ekran noktası), pid ya da ön."""
    if tool_name.startswith("desktop_background_"):
        pid = background_pid(args)
        return {"pid": pid} if pid is not None else {}
    frame = context.desktop.frame
    pixel = (_number(args.get("x")), _number(args.get("y")))
    if tool_name not in _POINT_TOOLS or frame is None or pixel[0] is None or pixel[1] is None:
        return {}
    if not frame.contains_pixel(pixel[0], pixel[1]):
        return {}
    point_x, point_y = frame.to_point(pixel[0], pixel[1])
    return {"point": [point_x, point_y]}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _element_label(raw: object) -> str:
    if not isinstance(raw, Mapping):
        return ""
    if raw.get("unverified"):
        return UNVERIFIED_ELEMENT
    role = str(raw.get("role") or "").removeprefix("AX")
    name = next(
        (str(raw[key]).strip() for key in ("title", "description", "help") if raw.get(key)), ""
    )
    return f"{role} '{name}'" if role and name else name or role


def _named_target(raw: str) -> tuple[str, str, int, str]:
    """`desktop_open` adı: yol ve `.app` atılır; paket kimliği biçimindeyse paket de sayılır.

    Ölçüldü (31 Ekim): yalnız tam ad karşılaştırılıyordu; "Binance.app" ya da
    "/Applications/Binance.app" ret listesine ve kategoriye takılmadan `open -a` ile açılıyordu.
    """
    name = raw.strip().rstrip("/").rsplit("/", 1)[-1].strip()
    if name.casefold().endswith(".app"):
        name = name[: -len(".app")].strip()
    bundle = name if "." in name and " " not in name else ""
    return name, bundle, 0, ""


async def resolve_target(
    tool_name: str, args: ToolArgs, context: ToolContext, probe: TargetProbe | None = None
) -> tuple[str, str, int, str, bool] | None:
    """(uygulama, paket, pid, öğe, sistem Calculator kanıtı); çözülemezse None."""
    if tool_name in _NAMED_TOOLS:
        app = args.get("app")
        return (*_named_target(app), False) if isinstance(app, str) and app.strip() else None
    if tool_name.startswith("desktop_background_") and background_pid(args) is None:
        # Geçersiz pid'de öndeki uygulamayı yoklamak yanlış hedefi değerlendirirdi.
        return None
    answer = await (probe or _swift_probe)(_probe_request(tool_name, args, context))
    if answer.get("ok") is not True or not isinstance(answer.get("app"), str):
        return None
    focused = context.desktop.focused_window
    if tool_name in _INTERACTIVE_TOOLS and focused is not None:
        window = answer.get("window")
        if (
            not isinstance(window, Mapping)
            or type(window.get("id")) is not int
            or context.desktop.focused_window_id <= 0
            or window.get("id") != context.desktop.focused_window_id
            or window.get("title") != context.desktop.focused_window_title
            or window.get("bounds") != list(focused[1:])
        ):
            return None
    pid = answer.get("pid")
    return (
        str(answer["app"]),
        str(answer.get("bundle") or ""),
        pid if type(pid) is int else 0,
        _element_label(answer.get("element")),
        answer.get("system_calculator") is True
        and answer.get("bundle") == "com.apple.calculator"
        and type(pid) is int
        and pid > 0,
    )


async def assess(
    tool_name: str, args: ToolArgs, context: ToolContext, probe: TargetProbe | None = None
) -> DesktopAssessment | None:
    """Masaüstü çağrısının politika kararı; belirli bir uygulamaya dokunmuyorsa None."""
    required = required_level(tool_name, args)
    if required is None:
        return None
    context.desktop.target_pid = 0
    if tool_name in _INTERACTIVE_TOOLS and context.desktop.focus_required:
        return DesktopAssessment(required, blocked=UNVERIFIED_REASON)
    resolved = await resolve_target(tool_name, args, context, probe)
    if resolved is None and tool_name.startswith("desktop_background_"):
        # Arka plan araçları zaten yardımcıyla çalışır: hedef doğrulanamıyorsa kapat (fail-closed).
        return DesktopAssessment(required, blocked=UNVERIFIED_REASON)
    if resolved is None:
        if tool_name in _INTERACTIVE_TOOLS and context.desktop.focused_window is not None:
            return DesktopAssessment(required, blocked=UNVERIFIED_REASON)
        return DesktopAssessment(required)
    app, bundle, pid, element, system_calculator = resolved
    focused = context.desktop.focused_window
    if tool_name in _INTERACTIVE_TOOLS and focused is not None and pid != focused[0]:
        return DesktopAssessment(
            required,
            blocked=(
                "Koordinattaki uygulama doğrulanmış odak hedefiyle uyuşmuyor; "
                "desktop_window_focus ve yeni desktop_screenshot ile hedefi yeniden doğrula."
            ),
        )
    # Gizleme (desktop.background=false) değerlendirilen hedefi korur (`desktop_turn`).
    context.desktop.target_pid = pid
    settings = context.desktop_settings
    level, category, reason = app_level(settings, app, bundle)
    warning = category.warning if category is not None else ""
    target = DesktopTarget(
        app or bundle,
        bundle,
        pid,
        level or DesktopLevel.OBSERVE,
        warning,
        element,
        system_calculator=system_calculator,
    )
    if level is None:
        return DesktopAssessment(required, target, blocked=reason)
    if level.rank < required.rank:
        hint = (
            category.warning
            if category is not None and category.key in {"browser", "finance", "terminal", "ide"}
            else LEVEL_SETTING_HINT
        )
        blocked = LEVEL_REASON.format(
            app=target.app, level=level.label, required=required.label, hint=hint
        )
        return DesktopAssessment(required, target, blocked=blocked)
    if required is DesktopLevel.OBSERVE:
        return DesktopAssessment(required, target)
    # Riskli eylem (P-008): gönder/sil/öde düğmesi, Terminal'de Enter, Sistem Ayarları.
    risky = risky_reason(tool_name, args, target, category.key if category is not None else "")
    return DesktopAssessment(required, target, risky=risky)


async def observe_effect(_args: ToolArgs, _context: ToolContext | None) -> ToolEffect:
    """Arka plan penceresine bakmak okumadır; çözücü yalnız onay kapısından (engel) geçirir.

    Ret listesindeki uygulamanın penceresi `desktop_background_screenshot/inspect` ile de
    okunmasın diye bu araçlar da `assess`'ten geçer; okuma olduğu için hiçbir kipte sorulmaz.
    """
    return ToolEffect.REMOTE_READ


def capture_exclusions(settings: DesktopSettings) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Ekran görüntüsünden çıkarılacak uygulamalar: (adlar, paket önekleri), küçük harf.

    Yalnız reddedilen uygulamalar. Claude'da View only kademesi "See the app in screenshots"
    demektir (#425): yatırım platformları görüntüde kalır. Fusion penceresi (ve CLI'de terminal)
    ayrıca her zaman çıkarılır (`desktop_screen`).
    """
    names = {item.strip().casefold() for item in settings.denied_apps if item.strip()}
    return tuple(sorted(names)), tuple(sorted(names))
