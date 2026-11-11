"""Masaüstü kararını onay isteğine işle: engel, uygulama başına oturum onayı, riskli eylem.

Claude Desktop'ın akışı (P-007): bir uygulama oturumda ilk kez kullanılacakken "Bu oturum /
Reddet" sorulur; onaydan sonra o uygulamadaki sıradan tıklama/yazma sorulmaz. Riskli eylem
(gönder/sil/öde düğmesi, Terminal'de Enter, Sistem Ayarları; P-008) her seferinde sorulur ve
oturum iznine dönüşmez. Engelli uygulama ya da yetmeyen kademe hiç sorulmadan kapanır.

Kip tablosu (`approval.py`'nin kurallarıyla):

- auto / edits / security: ilk kullanım sorulur, "Bu oturum" ile uygulama hatırlanır.
- plan: masaüstü eylemi yapılmaz (okuma değil).
- bypass: ilk kullanım yine sorulur (#446: Claude'da kip istisnası yok); riskli eylem yine
  sorulur, engel yine geçerlidir.

Hedef çözülemezse (Erişilebilirlik izni yok, yardımcı derlenemedi, nokta AX'te okunamadı)
ret listesi, engelli kategori ve Fusion koruması denetlenemez: çağrı `REMOTE_DESTRUCTIVE`
olur ve her kipte (İzinleri atla dahil) her seferinde sorulur, oturum iznine dönüşmez.
Ölçüldü (31 Ekim): bu durumda istek `REMOTE_WRITE` kalıyordu; bypass yalnız yıkıcıyı sorduğu
için `denied_apps=["1Password"]` ya da Fusion'ın onay kartı korumasız kalıyordu.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...core.desktop_ref_handles import canonical_arguments
from ...core.desktop_settings import DesktopLevel, DesktopTarget
from ...core.tools import ToolContext, ToolEffect
from ...tools.args import coerce_int
from ...tools.desktop_policy import UNVERIFIED_REASON, DesktopAssessment, _probe_request, assess
from ...tools.desktop_risk import _CALCULATOR_MATH_IDS, _bound_calculator_identity, _split_element

if TYPE_CHECKING:
    from .approval import ApprovalRequest

#: Uygulama başına ilk kullanım sorusunun gerekçesi (kart, terminal, uzak bildirim).
CONSENT_REASON = "Fusion {app} uygulamasını bu oturumda ilk kez kullanacak (kademe: {level})."
#: Oturum izninin kart açıklaması.
CONSENT_SCOPE = (
    "Bu oturum boyunca yalnız {app} için ({level}); riskli eylemler (gönder, sil, öde, "
    "Terminal'de Enter) yine her seferinde sorulur. Başka uygulama ayrıca sorulur."
)
#: Hedef çözülemediğinde kartta görünen gerekçe (her kipte, her seferinde sorulur).
UNKNOWN_TARGET_NOTE = (
    "Hedef uygulama okunamadı (Erişilebilirlik izni?); reddedilen uygulamalar denetlenemedi, "
    "bu çağrı her seferinde sorulur"
)
#: Engellenen masaüstü çağrısının modele dönen metni.
DESKTOP_BLOCKED_RESULT = (
    "Masaüstü eylemi engellendi, kullanıcıya sorulmadı: {reason}. Bu uygulamada bu eylemi "
    "deneme; önerilen yolu kullan ya da kullanıcıya Ayarlar › Bu bilgisayar'ı söyle."
)


@dataclass(frozen=True, slots=True)
class DesktopClickEvidence:
    """Odaklı pencere ve değerlendirmeden sonra tekrar yoklanacak yerel tıklama."""

    window_id: int
    recheck: Callable[[], Awaitable[bool]]


def blocked_result(request: ApprovalRequest) -> str:
    """Yerel hedef doğrulama engelini izin reddinden ayır; hiçbir engeli kaldırma."""
    if request.desktop_blocked and request.pre_denied == UNVERIFIED_REASON:
        return (
            f"Masaüstü eylemi engellendi, kullanıcıya sorulmadı: {request.pre_denied}. "
            "Pencereleri yeniden incele; güncel gerçek window_id ve pid ile "
            "desktop_window_focus kullanarak hedefi doğrula. Koordinat gerekiyorsa "
            "odaklamadan sonra yeni tam desktop_screenshot al. Bu yönlendirme izin "
            "vermez; tüm izin ve güvenlik denetimleri geçerlidir. Hedef hâlâ "
            "doğrulanamıyorsa somut başarısızlığı kullanıcıya dürüstçe bildir."
        )
    return DESKTOP_BLOCKED_RESULT.format(reason=request.pre_denied)


def is_desktop_consent(request: ApprovalRequest) -> bool:
    """Uygulama başına oturum onayı isteği mi? (bypass dahil her kipte sorulur, #446)."""
    key = request.consent_key
    return request.desktop_target is not None and key is not None and key.startswith("desktop:")


def consent_key(app_key: str) -> str:
    """Oturum izninin araçtan bağımsız anahtarı: aynı uygulamada tıklama ve yazma tek izin."""
    return f"desktop:{app_key}"


def apply_desktop(
    request: ApprovalRequest,
    assessment: DesktopAssessment | None,
    context: ToolContext | None = None,
) -> ApprovalRequest:
    """İsteği masaüstü kararıyla güncelle; karar yoksa olduğu gibi döndür.

    Uygulama onayı her zaman sorulur (#426: Claude'da istemi kapatan ayar yok; eski
    `desktop.app_consent` okunur ama uygulanmaz).
    """
    if assessment is None:
        return request
    target = assessment.target
    if assessment.blocked is not None:
        return replace(
            request,
            pre_denied=request.pre_denied or assessment.blocked,
            desktop_target=target,
            # Önce gelen izin kuralı engeli kendi metnini korur.
            desktop_blocked=request.pre_denied is None,
        )
    if target is None:
        if assessment.required is DesktopLevel.OBSERVE:
            return request
        # Fail-closed: engel denetlenemedi; bypass dahil sorulur ve hatırlanmaz (`danger`).
        return replace(
            request,
            effect=ToolEffect.REMOTE_DESTRUCTIVE,
            danger=request.danger or UNKNOWN_TARGET_NOTE,
            risk=UNKNOWN_TARGET_NOTE,
            unattended_safe=False,
            read_only=False,
        )
    if assessment.required is DesktopLevel.OBSERVE:
        # Bakmak (öne getirme, arka plan görüntüsü) onay gerektirmez; yalnız engel uygulanır.
        return replace(request, desktop_target=target)
    if assessment.risky is not None:
        return replace(
            request,
            effect=ToolEffect.REMOTE_DESTRUCTIVE,
            danger=request.danger or assessment.risky,
            risk=assessment.risky,
            unattended_safe=False,
            read_only=False,
            desktop_target=target,
        )
    level = target.level.label
    reason = CONSENT_REASON.format(app=target.app, level=level)
    note = f"{reason} {target.warning}".strip()
    return replace(
        request,
        effect=ToolEffect.REMOTE_INTERACT,
        risk=reason,
        unattended_safe=False,
        read_only=False,
        note=note,
        consent_key=consent_key(target.key),
        consent_alias=_name_alias(target),
        desktop_target=target,
        desktop_verified_press=_verified_calculator_press(request, target, context),
        desktop_click_evidence=_click_evidence(request, target, context),
    )


def _verified_calculator_press(
    request: ApprovalRequest, target: DesktopTarget, context: ToolContext | None
) -> bool:
    """Yerel uygulama kanıtı, odak kimliği ve doğrulanabilir düğme başvurusu birlikte gerekir."""
    if (
        request.tool.name != "desktop_background_action"
        or request.args.get("action") != "press"
        or not target.system_calculator
        or target.bundle != "com.apple.calculator"
        or context is None
        or context.desktop.focus_required
        or context.desktop.focused_window is None
        or context.desktop.focused_window[0] != target.pid
        or coerce_int(request.args.get("window_id")) != context.desktop.focused_window_id
    ):
        return False
    try:
        args = canonical_arguments(request.tool.name, request.args, context)
    except ValueError:
        return False
    identity = _bound_calculator_identity(args, target)
    return (
        identity is not None and identity[0] == "AXButton" and identity[2] in _CALCULATOR_MATH_IDS
    )


def _click_evidence(
    request: ApprovalRequest, target: DesktopTarget, context: ToolContext | None
) -> DesktopClickEvidence | None:
    name, args = request.tool.name, dict(request.args)
    if name != "desktop_click" and not (
        name == "desktop_mouse"
        and args.get("action", "click") == "click"
        and args.get("button", "left") == "left"
        and not args.get("modifiers")
    ):
        return None
    role, label = _split_element(target.element)
    if context is None or role != "Button" or not label.strip():
        return None
    view = context.desktop
    focus = view.focus_identity()
    if (
        view.focus_required
        or view.focused_window_id <= 0
        or view.focused_window is None
        or view.focused_window[0] != target.pid
        or "point" not in _probe_request(name, args, context)
    ):
        return None
    frame = view.frame

    async def recheck() -> bool:
        if view.focus_identity() != focus or view.frame != frame:
            return False
        current = await assess(name, args, context)
        return (
            current is not None
            and current.blocked is None
            and current.risky is None
            and current.target == target
            and view.focus_identity() == focus
            and view.frame == frame
        )

    return DesktopClickEvidence(view.focused_window_id, recheck)


def _name_alias(target: DesktopTarget) -> str | None:
    """Paketli hedefin ad anahtarı: toplu onay (#426) uygulamayı adla kaydeder."""
    if not target.bundle or not target.app:
        return None
    return consent_key(target.app.casefold())


def consent_description(request: ApprovalRequest) -> str | None:
    """ "Bu oturum" seçeneğinin açıklaması (yalnız uygulama onayı isteklerinde)."""
    target = request.desktop_target
    if target is None or request.consent_key is None:
        return None
    return CONSENT_SCOPE.format(app=target.app, level=target.level.label)
