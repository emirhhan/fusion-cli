"""Masaüstü eylem politikası: hedef uygulama, kademe tablosu ve engeller (P-007).

Claude Desktop computer use uygulama başına çalışır: ilk kullanımda "Allow for this session /
Deny" sorar, erişim kademesi kategoriye göre sabittir (tarayıcı = View only, terminal/IDE =
Click only, diğerleri = Full control), yatırım/kripto uygulamaları engellidir, Terminal /
Finder / System Settings ek uyarı taşır. Bu modül aynı kararı Fusion'ın araçları için verir:

1. Eylemin HEDEF uygulamasını çöz: tıklama noktasındaki pencerenin sahibi (AX), klavyede
   öndeki uygulama, arka plan araçlarında `pid`, `desktop_open`'da verilen ad.
2. Uygulamanın kademesini bul: ret listesi → Fusion'ın kendisi → `desktop.app_levels` →
   kategori tablosu → `desktop.control_level` tavanı.
3. Eylemin istediği kademeyle karşılaştır; yetmiyorsa ya da uygulama engelliyse çağrı
   sorulmadan kapanır (her kipte, `bypass` dahil). Oturum onayı ve riskli eylem kararı
   onay katmanındadır (`engines/agent/desktop_approval.py`).

Ölçüldü (31 Ekim): onay yalnız aracın etkisine göreydi (otomatik kipte her `desktop_click`
sorulur, bypass'ta hiç); hedef uygulama kavramı, oturum hatırlama ve kategori/engel listesi
yoktu: model Fusion'ın kendi onay kartına bile tıklayabilirdi.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from ..core.desktop_settings import DesktopLevel, DesktopSettings, DesktopTarget, parse_app_level
from ..core.tools import ToolArgs, ToolContext, ToolEffect
from .desktop_risk import risky_reason
from .native_desktop import SwiftDesktop

#: Hedef sorgusu: yardımcıya giden istek gövdesi → yanıt (testte sahte verilir).
TargetProbe = Callable[[dict[str, object]], Awaitable[Mapping[str, object]]]

BROWSER_HINT = "Web işi için chrome_* ya da browser_* araçlarını kullan."
SHELL_HINT = "Kabuk erişimine eşdeğer: komut için run_shell kullan."
LEVEL_SETTING_HINT = "Kademeyi Ayarlar › Bu bilgisayar'dan (desktop.app_levels) değiştirebilirsin."
DENIED_REASON = "{app} reddedilen uygulamalar listesinde (desktop.denied_apps)"
FUSION_REASON = "Fusion kendi penceresini yönetemez (kendi onay kartını onaylayamaz)"
CATEGORY_BLOCKED_REASON = (
    "{app} {label} uygulaması; varsayılan olarak engelli. Gerekirse kullanıcı "
    "desktop.app_levels ile açar"
)
LEVEL_REASON = "{app} için kademe '{level}', bu eylem '{required}' ister. {hint}"


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

    def matches(self, app: str, bundle: str) -> bool:
        name, ident = app.casefold(), bundle.casefold()
        if ident and any(ident.startswith(prefix) for prefix in self.bundles):
            return True
        return bool(name) and any(
            name == item or name.startswith(item + " ") for item in self.names
        )


#: Sıralıdır: ilk eşleşen kazanır (Fusion ve engelliler önce).
CATEGORIES: tuple[AppCategory, ...] = (
    AppCategory("fusion", "Fusion", None, FUSION_REASON, ("com.fusion.desktop",), ("fusion",)),
    AppCategory(
        "finance", "yatırım/kripto", None, "Yatırım ve kripto uygulamaları engelli.",
        ("com.binance", "com.coinbase", "com.krakenfx", "net.metaquotes", "com.tradingview",
         "com.robinhood", "com.interactivebrokers", "com.ledger", "com.exodus", "io.trezor",
         "org.electrum", "com.etoro", "com.webull", "com.tdameritrade"),
        ("binance", "coinbase", "kraken", "metatrader 4", "metatrader 5", "tradingview",
         "robinhood", "trader workstation", "ibkr desktop", "thinkorswim", "ledger live",
         "exodus", "trezor suite", "electrum", "etoro", "webull", "midas", "btcturk", "paribu",
         "matriks", "bitlo", "icrypex"),
    ),
    AppCategory(
        "secrets", "parola yöneticisi", None, "Parola yöneticileri engelli.",
        ("com.apple.keychainaccess", "com.apple.passwords", "com.1password", "com.agilebits",
         "com.bitwarden", "com.lastpass", "com.dashlane", "org.keepassxc"),
        ("keychain access", "anahtar zinciri erişimi", "passwords", "parolalar", "1password",
         "bitwarden", "lastpass", "dashlane", "keepassxc"),
    ),
    AppCategory(
        "browser", "tarayıcı", DesktopLevel.OBSERVE, BROWSER_HINT,
        ("com.apple.safari", "com.google.chrome", "org.mozilla.firefox", "com.microsoft.edgemac",
         "com.brave.browser", "company.thebrowser.browser", "com.operasoftware.opera",
         "com.vivaldi.vivaldi", "ru.yandex.desktop.yandex-browser", "org.chromium.chromium"),
        ("safari", "google chrome", "firefox", "microsoft edge", "brave browser", "arc", "opera",
         "vivaldi", "chromium", "yandex"),
    ),
    AppCategory(
        "terminal", "terminal", DesktopLevel.CLICK, SHELL_HINT,
        ("com.apple.terminal", "com.googlecode.iterm2", "dev.warp.warp", "net.kovidgoyal.kitty",
         "com.github.wez.wezterm", "io.alacritty", "org.alacritty", "com.mitchellh.ghostty"),
        ("terminal", "iterm", "iterm2", "warp", "kitty", "wezterm", "alacritty", "ghostty"),
    ),
    AppCategory(
        "ide", "IDE", DesktopLevel.CLICK, SHELL_HINT,
        ("com.microsoft.vscode", "com.todesktop.230313mzl4w4u92", "com.jetbrains.",
         "com.apple.dt.xcode", "dev.zed.zed", "com.sublimetext.", "com.exafunction.windsurf",
         "com.google.android.studio"),
        ("visual studio code", "code", "cursor", "xcode", "zed", "sublime text", "windsurf",
         "intellij idea", "pycharm", "webstorm", "android studio", "goland", "phpstorm"),
    ),
    AppCategory(
        "system", "Sistem Ayarları", DesktopLevel.FULL,
        "Sistem ayarlarını değiştirebilir; her eylem ayrıca sorulur.",
        ("com.apple.systempreferences", "com.apple.settings"),
        ("system settings", "system preferences", "sistem ayarları", "sistem tercihleri"),
    ),
    AppCategory(
        "finder", "Finder", DesktopLevel.FULL, "Her dosyayı okuyup yazabilir.",
        ("com.apple.finder",), ("finder",),
    ),
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class DesktopAssessment:
    """Bir masaüstü çağrısının politika kararı (onay katmanının girdisi)."""

    #: Eylemin istediği kademe.
    required: DesktopLevel
    #: Çözülen hedef; çözülemediyse None (çağrı eski temkinli onayla sorulur).
    target: DesktopTarget | None = None
    #: Sorulmadan kapanma gerekçesi (ret listesi, engelli kategori, yetmeyen kademe).
    blocked: str | None = None
    #: Riskli eylem gerekçesi (gönder/sil/öde, Terminal'de Enter; P-008): her seferinde sorulur.
    risky: str | None = None


def category_for(app: str, bundle: str) -> AppCategory | None:
    return next((item for item in CATEGORIES if item.matches(app, bundle)), None)


def _app_keys(app: str, bundle: str) -> frozenset[str]:
    return frozenset(item for item in (app.casefold(), bundle.casefold()) if item)


def app_level(
    settings: DesktopSettings, app: str, bundle: str = ""
) -> tuple[DesktopLevel | None, AppCategory | None, str]:
    """Uygulamanın kademesi (None = engelli), kategorisi ve engel gerekçesi."""
    keys = _app_keys(app, bundle)
    category = category_for(app, bundle)
    if any(item.strip().casefold() in keys for item in settings.denied_apps):
        return None, category, DENIED_REASON.format(app=app or bundle)
    if category is not None and category.key == "fusion":
        return None, category, FUSION_REASON
    override = next(
        (level for name, level in map(parse_app_level, settings.app_levels) if name in keys),
        None,
    )
    level = DesktopLevel.FULL
    if override is not None:
        level = override
    elif settings.category_defaults and category is not None:
        if category.level is None:
            reason = CATEGORY_BLOCKED_REASON.format(app=app or bundle, label=category.label)
            return None, category, reason
        level = category.level
    cap = settings.control_level
    return (level if level.rank <= cap.rank else cap), category, ""


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


def required_level(tool_name: str, args: ToolArgs) -> DesktopLevel | None:
    """Eylemin istediği kademe; belirli bir uygulamaya dokunmuyorsa None."""
    if tool_name == "desktop_mouse":
        action = args.get("action", "click")
        return DesktopLevel.FULL if action in _FULL_MOUSE_ACTIONS else DesktopLevel.CLICK
    if tool_name == "desktop_background_action":
        return DesktopLevel.FULL if args.get("action") == "set_value" else DesktopLevel.CLICK
    return _TOOL_LEVELS.get(tool_name)


async def _swift_probe(request: dict[str, object]) -> Mapping[str, object]:
    return await SwiftDesktop().invoke("target", {"kind": "probe", "request": request})


def _probe_request(tool_name: str, args: ToolArgs, context: ToolContext) -> dict[str, object]:
    """Yardımcıya sorulacak hedef: nokta (son görüntünün pikseli → ekran noktası), pid ya da ön."""
    pid = args.get("pid")
    if tool_name.startswith("desktop_background_") and type(pid) is int and pid > 0:
        return {"pid": pid}
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
    role = str(raw.get("role") or "").removeprefix("AX")
    name = next(
        (str(raw[key]).strip() for key in ("title", "description", "help") if raw.get(key)), ""
    )
    return f"{role} '{name}'" if role and name else name or role


async def resolve_target(
    tool_name: str, args: ToolArgs, context: ToolContext, probe: TargetProbe | None = None
) -> tuple[str, str, int, str] | None:
    """(uygulama, paket, pid, öğe) — çözülemezse None."""
    if tool_name in _NAMED_TOOLS:
        app = args.get("app")
        return (app.strip(), "", 0, "") if isinstance(app, str) and app.strip() else None
    answer = await (probe or _swift_probe)(_probe_request(tool_name, args, context))
    if answer.get("ok") is not True or not isinstance(answer.get("app"), str):
        return None
    pid = answer.get("pid")
    return (
        str(answer["app"]),
        str(answer.get("bundle") or ""),
        pid if type(pid) is int else 0,
        _element_label(answer.get("element")),
    )


async def assess(
    tool_name: str, args: ToolArgs, context: ToolContext, probe: TargetProbe | None = None
) -> DesktopAssessment | None:
    """Masaüstü çağrısının politika kararı; belirli bir uygulamaya dokunmuyorsa None."""
    required = required_level(tool_name, args)
    if required is None:
        return None
    resolved = await resolve_target(tool_name, args, context, probe)
    if resolved is None:
        return DesktopAssessment(required)
    app, bundle, pid, element = resolved
    settings = context.desktop_settings
    level, category, reason = app_level(settings, app, bundle)
    warning = category.warning if category is not None else ""
    target = DesktopTarget(
        app or bundle, bundle, pid, level or DesktopLevel.OBSERVE, warning, element
    )
    if level is None:
        return DesktopAssessment(required, target, blocked=reason)
    if level.rank < required.rank:
        hint = (
            category.warning
            if category is not None and category.key in {"browser", "terminal", "ide"}
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

    Reddedilen uygulamalar ve (kategori tablosu açıksa) engelli kategoriler; `app_levels` ile
    açıkça açılan uygulama hariç. Claude'da denied app'e "dokunulmaz"; Fusion ayrıca penceresini
    modele göstermez (P-007, P-033).
    """
    opened = {name for name, _level in map(parse_app_level, settings.app_levels)}
    names = {item.strip().casefold() for item in settings.denied_apps if item.strip()}
    prefixes = set(names)
    if settings.category_defaults:
        for category in CATEGORIES:
            if category.level is not None or category.key == "fusion":
                continue
            names.update(name for name in category.names if name not in opened)
            prefixes.update(category.bundles)
    return tuple(sorted(names - opened)), tuple(sorted(prefixes - opened))
