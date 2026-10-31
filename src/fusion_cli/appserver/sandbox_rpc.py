"""Masaüstü `sandbox.*` istekleri: Ayarlar › İzinler › Sandbox kartı (P-010).

    sandbox.durum    SandboxStatus (platform, kurulabilirlik, kurallar)
    sandbox.ayarla   {islem: ac|kapat|ag|izin|engelle|kaldir|oto|zorunlu|disari|sir|localhost,
                     deger?}
                     → güncel durum + notlar; yapılandırma kullanıcı dosyasına yazılır

İşlevler saf: oturum yalnız yapılandırmayı ve kökü verir, güncel yapılandırmayı alır.
Değişiklik bir SONRAKİ turda uygulanır (araç bağlamı tur başında kurulur).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..config.models import Config
from ..config.sandbox_admin import apply_sandbox_action, sandbox_status
from ..core.errors import ConfigError

SANDBOX_ROUTES = frozenset({"sandbox.durum", "sandbox.ayarla"})


def dispatch_sandbox(
    name: str, data: Mapping[str, object], config: Config, root: Path
) -> tuple[Config | None, dict[str, object]]:
    """İsteği yanıtla; yapılandırma değiştiyse yenisini de döndür."""
    if name == "sandbox.durum":
        return None, sandbox_status(config, root).as_dict()
    action = data.get("islem")
    value = data.get("deger", "")
    if not isinstance(action, str) or not isinstance(value, (str, bool)):
        return None, {"ok": False, "metin": "islem metin, deger metin ya da boolean olmalı."}
    raw = ("on" if value else "off") if isinstance(value, bool) else value
    try:
        change = apply_sandbox_action(config, action, raw, root=root)
    except ConfigError as error:
        return None, {"ok": False, "metin": str(error)}
    return change.config, {
        **sandbox_status(change.config, root).as_dict(),
        "dosya": str(change.path),
        "notlar": list(change.notes),
    }
