"""macOS Erişilebilirlik ve Ekran Kaydı izinleri: ön kontrol, istem, ayar bağlantısı (P-005).

Masaüstü araçları izin yoksa yapısal bir sonuç döner (`structured["izin_gerekli"]`); masaüstü
uygulaması bunu görüp izin kartını açar. İstem (`request`) TCC penceresini bu süreç için
açar; Fusion.app altındaki sidecar'da sorumlu süreç Fusion.app'tir, izin listesinde
"Fusion" görünür. Ölçüldü (31 Ekim): eskiden yalnız `AXIsProcessTrusted` okunup metin
dönülüyordu; Ekran Kaydı hiç yoklanmıyordu ve `screencapture` izinsizken sessizce yalnız
masaüstü arka planını veriyordu.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from ..core.tools import ToolResult

ACCESSIBILITY = "accessibility"
SCREEN_RECORDING = "screen_recording"
PERMISSION_KINDS = (ACCESSIBILITY, SCREEN_RECORDING)

GRANTED = "granted"
DENIED = "denied"
UNSUPPORTED = "unsupported"

SETTINGS_URLS = {
    ACCESSIBILITY: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    SCREEN_RECORDING: (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
    ),
}
TITLES = {ACCESSIBILITY: "Erişilebilirlik", SCREEN_RECORDING: "Ekran Kaydı"}
#: Modele dönen metinler. Eski sabit (`desktop.ACCESSIBILITY_ERROR`) bunun aynısıdır.
MESSAGES = {
    ACCESSIBILITY: (
        "macOS Erişilebilirlik izni yok. Sistem Ayarları > Gizlilik ve Güvenlik > "
        "Erişilebilirlik bölümünde Fusion'a izin ver; sonra uygulamayı yeniden aç."
    ),
    SCREEN_RECORDING: (
        "macOS Ekran Kaydı izni yok. Sistem Ayarları > Gizlilik ve Güvenlik > "
        "Ekran Kaydı bölümünde Fusion'a izin ver; sonra uygulamayı yeniden aç."
    ),
}

_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_APPLICATION_SERVICES = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)


@dataclass(frozen=True, slots=True)
class DesktopPermissionStatus:
    """İki iznin anlık durumu; `platform` macOS dışında `unsupported`."""

    accessibility: str
    screen_recording: str

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": True,
            "platform": "macos" if sys.platform == "darwin" else sys.platform,
            ACCESSIBILITY: self.accessibility,
            SCREEN_RECORDING: self.screen_recording,
            "ayarlar": dict(SETTINGS_URLS),
        }


def permission_failure(kind: str) -> ToolResult:
    """İzin eksik: modele Türkçe yönerge, arayüze yapısal `izin_gerekli` işareti."""
    return ToolResult.failure(
        MESSAGES[kind],
        structured={"izin_gerekli": kind, "ayar_baglantisi": SETTINGS_URLS[kind]},
    )


def missing_permission_from_output(output: str) -> str | None:
    """Araç çıktısındaki izin metninden hangi iznin eksik olduğunu bul (olay sinki için)."""
    for kind, message in MESSAGES.items():
        if message in output:
            return kind
    return None


def _application_services() -> ctypes.CDLL:
    return ctypes.CDLL(_APPLICATION_SERVICES)


def _accessibility_trusted(framework: ctypes.CDLL) -> bool:
    framework.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(framework.AXIsProcessTrusted())


def _screen_capture_allowed(framework: ctypes.CDLL) -> bool:
    """`CGPreflightScreenCaptureAccess` (10.15+): istem açmadan Ekran Kaydı durumunu okur."""
    framework.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
    return bool(framework.CGPreflightScreenCaptureAccess())


def probe() -> DesktopPermissionStatus:
    """İstem AÇMADAN iki iznin durumunu oku."""
    if sys.platform != "darwin":
        return DesktopPermissionStatus(UNSUPPORTED, UNSUPPORTED)
    try:
        framework = _application_services()
        accessibility = GRANTED if _accessibility_trusted(framework) else DENIED
        screen = GRANTED if _screen_capture_allowed(framework) else DENIED
    except (OSError, AttributeError):
        return DesktopPermissionStatus(UNSUPPORTED, UNSUPPORTED)
    return DesktopPermissionStatus(accessibility, screen)


def _prompt_accessibility(framework: ctypes.CDLL) -> bool:
    """`AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: true})`."""
    core = ctypes.CDLL(_CORE_FOUNDATION)
    key = ctypes.c_void_p.in_dll(framework, "kAXTrustedCheckOptionPrompt")
    true = ctypes.c_void_p.in_dll(core, "kCFBooleanTrue")
    keys = (ctypes.c_void_p * 1)(key.value)
    values = (ctypes.c_void_p * 1)(true.value)
    core.CFDictionaryCreate.restype = ctypes.c_void_p
    core.CFDictionaryCreate.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    key_callbacks = ctypes.addressof(ctypes.c_char.in_dll(core, "kCFTypeDictionaryKeyCallBacks"))
    value_callbacks = ctypes.addressof(
        ctypes.c_char.in_dll(core, "kCFTypeDictionaryValueCallBacks")
    )
    options = core.CFDictionaryCreate(None, keys, values, 1, key_callbacks, value_callbacks)
    if not options:
        raise OSError("İzin seçenekleri oluşturulamadı.")
    framework.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
    framework.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
    core.CFRelease.argtypes = [ctypes.c_void_p]
    try:
        return bool(framework.AXIsProcessTrustedWithOptions(options))
    finally:
        core.CFRelease(options)


def _prompt_screen_capture(framework: ctypes.CDLL) -> bool:
    """`CGRequestScreenCaptureAccess`: istem bir kez açılır; izin sonrası yeniden açılış gerekir."""
    framework.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
    return bool(framework.CGRequestScreenCaptureAccess())


def request(kind: str) -> DesktopPermissionStatus:
    """Sistem istemini aç (gerekirse) ve güncel durumu döndür; bilinmeyen tür `ValueError`."""
    if kind not in PERMISSION_KINDS:
        raise ValueError(f"Bilinmeyen masaüstü izni: {kind!r}")
    if sys.platform != "darwin":
        return probe()
    try:
        framework = _application_services()
        if kind == ACCESSIBILITY:
            _prompt_accessibility(framework)
        else:
            _prompt_screen_capture(framework)
    except (OSError, AttributeError, ValueError):
        return probe()
    return probe()
