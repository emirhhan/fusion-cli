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

from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.desktop_settings import DesktopLevel, DesktopTarget
from ...core.tools import ToolEffect
from ...tools.desktop_policy import UNVERIFIED_REASON, DesktopAssessment

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
    request: ApprovalRequest, assessment: DesktopAssessment | None
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
    )


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
