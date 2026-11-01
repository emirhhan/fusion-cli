"""Projenin çalışan önizleme/dev sunucularının yerel kökenleri onaysız açılır (#438).

Claude Code Desktop: "Your local dev servers and project files don't need approval";
Chrome belgesindeki temel örnek `open localhost:3000`'dir. Fusion'da yerel adres yalnız
kullanıcı o kökeni mesajında yazdıysa açılıyordu; ajanın kendi başlattığı önizleme sunucusu
bile reddediliyordu. Artık bu köke ait çalışan önizlemelerin (`.claude/launch.json` adlı
yapılandırmalar ve statik önizleme) kökenleri turun canlı izin kümesine eklenir. Diğer özel ağ
adresleri, metadata ucu ve bilinmeyen yerel portlar kapalı kalır.
"""

from __future__ import annotations

from ..core.tools import ToolContext
from . import preview_launch, preview_server
from .web import loopback_origin


def project_preview_origins(context: ToolContext) -> set[str]:
    """Bu kökte çalışan önizlemelerin `host:port` kökenleri."""
    urls = [preview.url for _name, preview in preview_launch.running_launches(context.root)]
    static = preview_server.running(context.root)
    if static is not None:
        urls.append(static.url)
    return {origin for origin in map(loopback_origin, urls) if origin is not None}


def allowed_local(context: ToolContext) -> set[str]:
    """Canlı izin kümesi (`context.local_origins`) + projenin önizleme kökenleri.

    Küme yerinde güncellenir: tarayıcının istek kapısı (`install_request_guard`) aynı canlı
    kümeyi okur, alt istekler de aynı kuralla geçer.
    """
    context.local_origins.update(project_preview_origins(context))
    return context.local_origins
