"""Telefonun gerçekten açabileceği adres: tünel (Tailscale) DNS adını bulur.

Ölçüldü (31 Ekim): `fusion remote-control` adres ve QR olarak `http://127.0.0.1:PORT` basıyordu;
telefon QR'ı okuyunca kendi localhost'una gidiyordu. Sunucu 127.0.0.1'e bağlanır, telefon ona
yalnız `tailscale serve` (ya da benzeri) tünelinden ulaşır; o adres burada okunur. Yalnız
okuma: `tailscale status --json` çalıştırılır, ağ isteği yapılmaz, sır içermez.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable

#: `tailscale status --json` için üst sınır; komut takılırsa adres yok sayılır.
TAILSCALE_STATUS_TIMEOUT_SECONDS = 2.0
#: Mac App Store kurulumu PATH'e `tailscale` koymaz; bilinen ikili konumu.
TAILSCALE_MAC_APP_BINARY = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"

Runner = Callable[[list[str]], str]


def _default_runner(args: list[str]) -> str:
    completed = subprocess.run(  # sabit komut, kullanıcı girdisi yok
        args, capture_output=True, text=True, timeout=TAILSCALE_STATUS_TIMEOUT_SECONDS, check=False
    )
    return completed.stdout if completed.returncode == 0 else ""


def tailscale_binary() -> str:
    found = shutil.which("tailscale")
    if found:
        return found
    return TAILSCALE_MAC_APP_BINARY if shutil.which(TAILSCALE_MAC_APP_BINARY) else ""


def tailscale_https_url(*, runner: Runner | None = None) -> str:
    """`https://<makine>.<tailnet>.ts.net` ya da Tailscale yoksa/okunamazsa boş.

    `tailscale serve --https=443` tam bu adreste dinler; başka port kullanıldıysa kullanıcı
    `--adres` ile kendi adresini verir.
    """
    args = [tailscale_binary() or "tailscale", "status", "--json"]
    try:
        raw = (runner or _default_runner)(args)
        data = json.loads(raw)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    if not isinstance(data, dict):
        return ""
    self_node = data.get("Self")
    dns_name = self_node.get("DNSName") if isinstance(self_node, dict) else None
    if not isinstance(dns_name, str) or not dns_name.strip():
        return ""
    return f"https://{dns_name.strip().rstrip('.')}"
