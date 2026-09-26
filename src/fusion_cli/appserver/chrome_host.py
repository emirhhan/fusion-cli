"""Chrome eklentisinin Fusion'ı KENDİSİ bulması: yerel mesajlaşma (native messaging).

Eskiden eklenti yan panelde kullanıcının port ve anahtarı elle yapıştırmasını
bekliyordu. Claude in Chrome'daki gibi artık eklenti arka planda Chrome'un yerel
mesajlaşma kanalıyla bu sunucuya "pair" der; sunucu çalışan Fusion köprüsünün
port ve anahtarını verir.

Bilgi, köprü açılınca `chrome-bridge.json` dosyasına yalnız kullanıcının
okuyabileceği izinle (0600) yazılır; sahibi süreç ölmüşse dosya yok sayılır.
Chrome yalnız `allowed_origins` listesindeki eklentinin bu sunucuyu
başlatmasına izin verir; kimlik, paketlenmemiş eklentinin klasör yolundan
Chrome'un kendi yöntemiyle hesaplanır.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import struct
import sys
from pathlib import Path
from typing import Any, BinaryIO

from ..config.paths import base_config_dir

HOST_NAME = "com.fusion.browser"
#: Chrome yerel mesajlaşma iletisi üst sınırı (host → Chrome yönü 1 MB).
_MAX_MESSAGE = 1024 * 1024


def bridge_state_file() -> Path:
    return base_config_dir() / "chrome-bridge.json"


def write_bridge_state(port: int, token: str, pid: int | None = None) -> None:
    yol = bridge_state_file()
    yol.parent.mkdir(parents=True, exist_ok=True)
    veri = json.dumps({"port": port, "anahtar": token, "pid": pid or os.getpid()})
    fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(veri)


def clear_bridge_state(pid: int | None = None) -> None:
    """Yalnız bu sürecin yazdığı durumu sil; başka sekmenin köprüsünü ezme."""
    yol = bridge_state_file()
    with contextlib.suppress(OSError, ValueError):
        if json.loads(yol.read_text(encoding="utf-8")).get("pid") == (pid or os.getpid()):
            yol.unlink()


def read_bridge_state() -> dict[str, Any] | None:
    try:
        veri = json.loads(bridge_state_file().read_text(encoding="utf-8"))
        os.kill(int(veri["pid"]), 0)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return {"port": int(veri["port"]), "anahtar": str(veri["anahtar"])}


def extension_id_for_path(path: Path) -> str:
    """Chrome'un paketlenmemiş eklenti kimliği: yolun SHA-256'sı, a-p alfabesiyle."""
    ozet = hashlib.sha256(str(path).encode()).hexdigest()[:32]
    return "".join(chr(ord("a") + int(harf, 16)) for harf in ozet)


def _read_message(stream: BinaryIO) -> dict[str, Any] | None:
    baslik = stream.read(4)
    if len(baslik) < 4:
        return None
    (uzunluk,) = struct.unpack("<I", baslik)
    if uzunluk > _MAX_MESSAGE:
        return None
    veri = json.loads(stream.read(uzunluk) or b"{}")
    return veri if isinstance(veri, dict) else {}


def _write_message(stream: BinaryIO, veri: dict[str, Any]) -> None:
    govde = json.dumps(veri).encode()
    stream.write(struct.pack("<I", len(govde)) + govde)
    stream.flush()


def serve(stdin: BinaryIO, stdout: BinaryIO) -> None:
    """Tek ileti al, cevapla (Chrome `sendNativeMessage` her çağrıda yeni süreç açar)."""
    mesaj = _read_message(stdin)
    if mesaj is None:
        return
    if mesaj.get("type") != "pair":
        _write_message(stdout, {"ok": False, "hata": "Bilinmeyen istek."})
        return
    durum = read_bridge_state()
    if durum is None:
        _write_message(stdout, {"ok": False, "hata": "Fusion köprüsü çalışmıyor."})
        return
    _write_message(stdout, {"ok": True, **durum})


def _host_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "chrome-host"]
    return [sys.executable, "-m", "fusion_cli.appserver.chrome_host"]


def _chrome_host_dirs(home: Path) -> list[Path]:
    destek = home / "Library" / "Application Support"
    return [
        destek / "Google" / "Chrome" / "NativeMessagingHosts",
        destek / "Chromium" / "NativeMessagingHosts",
    ]


EXTENSION_NAME = "Fusion Browser"


def installed_extension_ids(home: Path | None = None) -> set[str]:
    """Chrome profillerinde "Fusion Browser" adıyla yüklü eklentilerin kimlikleri."""
    kok = (home or Path.home()) / "Library" / "Application Support" / "Google" / "Chrome"
    kimlikler: set[str] = set()
    for dosya in [*kok.glob("*/Preferences"), *kok.glob("*/Secure Preferences")]:
        try:
            ayarlar = json.loads(dosya.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        uzantilar = ayarlar.get("extensions", {}).get("settings", {}) or {}
        for kimlik, bilgi in uzantilar.items():
            manifest = bilgi.get("manifest") or {} if isinstance(bilgi, dict) else {}
            yol = str(bilgi.get("path", "")) if isinstance(bilgi, dict) else ""
            if manifest.get("name") == EXTENSION_NAME or yol.endswith("/chrome-extension"):
                kimlikler.add(kimlik)
    return kimlikler


def candidate_extension_ids(home: Path | None = None) -> set[str]:
    """Kaynak ağacı, kurulu uygulama ve Chrome'da yüklü eklentilerden kimlikler."""
    dizinler = [
        Path(__file__).resolve().parents[3] / "chrome-extension",
        Path("/Applications/Fusion.app/Contents/Resources/chrome-extension"),
    ]
    return {extension_id_for_path(d) for d in dizinler} | installed_extension_ids(home)


def install_native_host(extension_ids: set[str], home: Path | None = None) -> list[Path]:
    """Başlatıcı betiği ve Chrome'un yerel mesajlaşma bildirimini yaz (macOS).

    `FUSION_NO_NATIVE_HOST` tanımlıysa (testler) hiçbir şey yazılmaz.
    """
    if sys.platform != "darwin" or os.environ.get("FUSION_NO_NATIVE_HOST"):
        return []
    home = home or Path.home()
    betik = base_config_dir() / "chrome-host.sh"
    betik.parent.mkdir(parents=True, exist_ok=True)
    komut = " ".join(f"'{parca}'" for parca in _host_command())
    betik.write_text(f"#!/bin/sh\nexec {komut}\n", encoding="utf-8")
    betik.chmod(0o755)
    bildirim = {
        "name": HOST_NAME,
        "description": "Fusion Browser yerel eşleşme",
        "path": str(betik),
        "type": "stdio",
        "allowed_origins": sorted(f"chrome-extension://{kimlik}/" for kimlik in extension_ids),
    }
    yazilan: list[Path] = []
    for dizin in _chrome_host_dirs(home):
        if not dizin.parent.is_dir():
            continue
        dizin.mkdir(exist_ok=True)
        hedef = dizin / f"{HOST_NAME}.json"
        hedef.write_text(json.dumps(bildirim, indent=2), encoding="utf-8")
        yazilan.append(hedef)
    return yazilan


def main() -> None:
    serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
