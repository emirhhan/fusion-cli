"""Toplu uygulama onayı (#426): Claude computer use `request_access` karşılığı.

Claude'da model işe başlamadan kullanacağı uygulamaları tek istemde ister; istem hangi
uygulamaların denetleneceğini, istenen ek izinleri ve çalışırken kaç uygulamanın gizleneceğini
gösterir; seçenekler "Allow for this session" / "Deny". Fusion'da aynı istem
`desktop_request_access` aracıyla gelir: onaylanan her uygulama, ilk tıklamada ayrıca
sorulmadan oturum boyu izinli olur (`consent_key` + `extra_consent_keys`).

Ek izin: Claude pano okuma/yazma izni ister çünkü pano araçları vardır; Fusion'da pano aracı
yok, bu yüzden istemde ek izin satırı yalnız gerçekten istenen bir izin olduğunda çıkar ve şu
an hiçbir araç ek izin istemez.

Bu modül araç katmanındadır: uygulama adlarını ayrıştırır, kademe/ret listesini değerlendirir
ve gizlenecek uygulama sayısını hesaplar. Onay isteğine işleme `engines/agent/desktop_access.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..core.desktop_settings import DesktopSettings, DesktopTarget
from ..core.tools import ToolArgs, ToolContext, ToolResult
from . import desktop_turn
from .desktop_policy import app_level, category_for, normalize_app

#: Aracın adı (Claude: `request_access`; Fusion masaüstü ailesi `desktop_` önekini taşır).
ACCESS_TOOL = "desktop_request_access"
#: Tek istemde istenebilecek en fazla uygulama (kart okunur kalsın).
MAX_APPS = 10

#: Ekrandaki pencere sahipleri; okunamazsa None (testte sahte verilir).
OwnerReader = Callable[[], tuple[str, ...] | None]


@dataclass(frozen=True, slots=True)
class AccessPlan:
    """İstenen uygulamaların değerlendirmesi: izin verilebilenler ve engelliler."""

    allowed: tuple[DesktopTarget, ...]
    #: (uygulama, engel gerekçesi) çiftleri; sorulmadan dışarıda kalır.
    blocked: tuple[tuple[str, str], ...]
    #: Çalışırken gizlenecek diğer uygulama sayısı; None = gizlenmez ya da okunamadı.
    hidden_count: int | None


def requested_apps(args: ToolArgs) -> tuple[str, ...]:
    """`apps` listesini (ya da virgüllü metni) ayrıştır; tekrarlar ve boşluklar atılır."""
    raw = args.get("apps")
    items: Iterable[object]
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, list | tuple):
        items = raw
    else:
        items = ()
    seen: set[str] = set()
    apps: list[str] = []
    for item in items:
        name = _clean_name(item)
        key = normalize_app(name)
        if name and key not in seen:
            seen.add(key)
            apps.append(name)
    return tuple(apps[:MAX_APPS])


def _clean_name(item: object) -> str:
    if not isinstance(item, str):
        return ""
    name = item.strip().rstrip("/").rsplit("/", 1)[-1].strip()
    if name.casefold().endswith(".app"):
        name = name[: -len(".app")].strip()
    return name


def plan_access(
    settings: DesktopSettings, apps: Iterable[str], owners: OwnerReader | None = None
) -> AccessPlan:
    """Her uygulamanın kademesini ve engelini çöz; gizlenecek uygulamaları say."""
    allowed: list[DesktopTarget] = []
    blocked: list[tuple[str, str]] = []
    for app in apps:
        bundle = app if "." in app and " " not in app else ""
        level, category, reason = app_level(settings, app, bundle)
        if level is None:
            blocked.append((app, reason))
            continue
        warning = category.warning if category is not None else ""
        allowed.append(DesktopTarget(app, bundle, 0, level, warning))
    hidden = _hidden_count(settings, allowed, owners)
    return AccessPlan(tuple(allowed), tuple(blocked), hidden)


def _hidden_count(
    settings: DesktopSettings, allowed: Iterable[DesktopTarget], owners: OwnerReader | None
) -> int | None:
    """Gizlenecek uygulama sayısı: ekrandakiler − istenenler − Fusion (`desktop_turn`)."""
    if desktop_turn.turn_settings(settings).background:
        return None
    if owners is None:
        from .desktop_visibility import onscreen_owners

        owners = onscreen_owners
    names = owners()
    if names is None:
        return None
    keep = {normalize_app(target.app) for target in allowed}
    others = {
        normalize_app(name)
        for name in names
        if name and normalize_app(name) not in keep and not _is_fusion(name)
    }
    return len(others)


def _is_fusion(app: str) -> bool:
    category = category_for(app, "")
    return category is not None and category.key == "fusion"


def describe(plan: AccessPlan) -> str:
    """Onay kartı ve terminal istemindeki metin (uygulamalar, ek izin, gizlenecek sayı)."""
    apps = ", ".join(f"{target.app} ({target.level.label})" for target in plan.allowed)
    lines = [f"Fusion bu oturumda şu uygulamaları denetlemek istiyor: {apps}."]
    if plan.hidden_count is not None:
        lines.append(f"Çalışırken diğer {plan.hidden_count} uygulama gizlenecek.")
    if plan.blocked:
        names = ", ".join(app for app, _ in plan.blocked)
        lines.append(f"İstenmeyecek (engelli): {names}.")
    return " ".join(lines)


def desktop_request_access(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Onaydan SONRA çalışır: izin verilen ve dışarıda kalan uygulamaları modele söyler."""
    apps = requested_apps(args)
    if not apps:
        return ToolResult("apps boş: kullanılacak uygulama adlarını liste olarak ver.", ok=False)
    plan = plan_access(context.desktop_settings, apps, owners=lambda: ())
    parts: list[str] = []
    if plan.allowed:
        names = ", ".join(target.app for target in plan.allowed)
        parts.append(f"Bu oturum için izin verildi: {names}. Bu uygulamalarda ilk eylem sorulmaz.")
    for app, reason in plan.blocked:
        parts.append(f"{app}: {reason}")
    return ToolResult(" ".join(parts), ok=bool(plan.allowed))
