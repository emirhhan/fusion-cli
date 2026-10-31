"""Fusion'ın açtığı Chrome'ların hata ayıklama (CDP) portları: sandbox'a kapatılır (P-010).

Web model sağlayıcılarının paylaşılan Chrome'u (`providers.web_shared_browser`) profil
başına tek süreçtir, birden çok `fusion app` süreci ona loopback CDP portundan bağlanır;
port kimlik doğrulamasızdır. Ölçüldü (1 Kasım): ağ `open` ya da `allow_localhost` açıkken
sandbox'taki `curl 127.0.0.1:<port>` yanıt alıyordu; port dosyası okuma engelinde olsa da
port taranarak bulunur ve oturumlu tarayıcı sürülebilirdi.

`--remote-debugging-pipe`'a geçilmedi: boru tarayıcıyı açan TEK sürece bağlıdır, oysa
Chrome başlatan süreçten bağımsız yaşar (`start_new_session`, kira dosyaları) ve diğer
sekme süreçleri ona bağlanır; boru için ayrı bir aracı süreç (yeni süreç modeli) gerekirdi.
Ajanın `browser_*` tarayıcısı ve doğrulama tarayıcıları Playwright `launch` ile zaten boru
kullanır, portu yoktur. Bu yüzden port, sandbox ağ kuralında (Seatbelt) ve proxy'de reddedilir.
"""

from __future__ import annotations

from pathlib import Path

from ..config.paths import web_profiles_root
from ..core.constants import DEVTOOLS_PORT_FILE

__all__ = ["fusion_debug_ports"]

#: Geçerli TCP port aralığı.
_MAX_PORT = 65_535


def _read_port(path: Path) -> int | None:
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        port = int(first_line.strip())
    except (OSError, IndexError, ValueError):
        return None
    return port if 0 < port <= _MAX_PORT else None


def fusion_debug_ports(root: Path | None = None) -> tuple[int, ...]:
    """Web profillerinin (`web_profiles/<sağlayıcı>/<hesap>`) yazdığı CDP portları, sıralı.

    Chrome kapanınca Fusion port dosyasını siler; kalmış eski bir dosya yalnız o portu
    (geçici port aralığında) gereksiz yere kapatır, zarar vermez.
    """
    base = root or web_profiles_root()
    ports = (_read_port(path) for path in base.glob(f"*/*/{DEVTOOLS_PORT_FILE}"))
    return tuple(sorted({port for port in ports if port is not None}))
