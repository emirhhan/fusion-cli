"""`launch.json` portu doluysa ne yapılacağı (`autoPort`) ve `${port}` yer tutucusu.

Ölçüldü (31 Ekim, P-041): `autoPort` alanı uyarıyla yok sayılıyordu; port başka bir süreçte
açıkken komut aynı porta bağlanmaya çalışıp düşüyor, panel 45 sn sonra "yanıt vermedi"
diyordu — üstelik o portta yanıt veren BAŞKA sunucu varsa önizleme yanlış uygulamayı
gösteriyordu. Claude Code masaüstündeki anlamı izlenir:

- `autoPort: true` ya da alan yok → port doluysa sıradaki boş port seçilir, komuta `PORT`
  ortam değişkeniyle (ve `runtimeArgs` içindeki `${port}` ile) verilir;
- `autoPort: false` → port doluysa başlatılmaz, anlaşılır hata döner.

Sunucu `PORT`'u okumuyorsa (Vite `--port` ister) `runtimeArgs`'a `"--port", "${port}"` yazılır.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

#: `runtimeArgs` içinde seçilen portla değiştirilen yer tutucu.
PORT_PLACEHOLDER = "${port}"
#: Dolu portun ardından denenecek en fazla port sayısı.
PORT_SCAN_SPAN = 50


@dataclass(frozen=True, slots=True)
class PortChoice:
    """Kullanılacak port; `requested`'dan farklıysa port dolu olduğu için kaydırılmıştır."""

    requested: int
    port: int

    @property
    def moved(self) -> bool:
        return self.port != self.requested


def is_port_busy(port: int) -> bool:
    """Port yerelde kullanımda mı? IPv4'te bind denenir, IPv6 loopback'te bağlanılır.

    Bind sınaması `preview_server.free_port` ile aynı gerekçeyle: bağlantı reddi portun boş
    olduğunu kanıtlamaz. Vite gibi sunucular yalnız `::1`'e bağlanabildiği için o da yoklanır.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return True
    try:
        with socket.create_connection(("::1", port), timeout=0.2):
            return True
    except OSError:
        return False


def choose_port(requested: int, *, auto_port: bool | None) -> PortChoice | None:
    """Port boşsa kendisi; doluysa `auto_port` False değilse sıradaki boş port.

    Dönüş None: port dolu ve `autoPort: false` (çağıran hata verir) ya da tarama aralığında
    boş port yok.
    """
    if not is_port_busy(requested):
        return PortChoice(requested, requested)
    if auto_port is False:
        return None
    for candidate in range(requested + 1, min(requested + 1 + PORT_SCAN_SPAN, 65_536)):
        if not is_port_busy(candidate):
            return PortChoice(requested, candidate)
    return None


def with_port(url: str, port: int) -> str:
    """Adresin portunu değiştir (yalnız portu; şema, ana makine ve yol korunur)."""
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    return urlunparse(parsed._replace(netloc=f"{host}:{port}"))


def url_port(url: str | None) -> int | None:
    """Adresteki açık port; yoksa ya da çözülemezse None."""
    if not url:
        return None
    try:
        return urlparse(url).port
    except ValueError:
        return None


def expand_port(args: tuple[str, ...], port: int) -> tuple[str, ...]:
    """`runtimeArgs` içindeki `${port}` yer tutucularını seçilen portla değiştir."""
    return tuple(arg.replace(PORT_PLACEHOLDER, str(port)) for arg in args)
