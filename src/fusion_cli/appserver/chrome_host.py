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
import importlib
import json
import os
import shlex
import stat
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from ..config.paths import base_config_dir
from .native_host_paths import host_dirs, windows_host_keys

HOST_NAME = "com.fusion.browser"
#: Chrome yerel mesajlaşma iletisi üst sınırı (host → Chrome yönü 1 MB).
_MAX_MESSAGE = 1024 * 1024


def bridge_state_file() -> Path:
    return base_config_dir() / "chrome-bridge.json"


def write_bridge_state(port: int, token: str, pid: int | None = None) -> None:
    yol = bridge_state_file()
    yol.parent.mkdir(parents=True, exist_ok=True)
    veri = json.dumps({"port": port, "anahtar": token, "pid": pid or os.getpid()})
    # Atomik yayım: okuyan (host/başka çekirdek) `O_TRUNC` anında boş/yarım dosya görüp "köprü
    # çalışmıyor" sanmasın; `mkstemp` 0600 oluşturur, `replace` mevcut dosyanın izni gevşekse
    # de onu sıkılaştırır (ölçüldü 30 Ekim: izin yalnız oluşturmada uygulanıyordu).
    fd, geciciad = tempfile.mkstemp(prefix=f".{yol.name}.", dir=yol.parent)
    gecici = Path(geciciad)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(veri)
        gecici.chmod(stat.S_IRUSR | stat.S_IWUSR)
        gecici.replace(yol)
    finally:
        gecici.unlink(missing_ok=True)


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
    try:
        veri = json.loads(stream.read(uzunluk) or b"{}")
    except ValueError:
        # Bozuk/kısa okunan gövde süreci traceback ile çökertmesin (Chrome'a boş yanıt).
        return None
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


def _chrome_host_dirs(home: Path, platform: str | None = None) -> list[Path]:
    """Chrome, Chromium, Edge, Brave, Arc, Vivaldi, Opera dizinleri (#433)."""
    return host_dirs(home, sys.platform if platform is None else platform)


EXTENSION_NAME = "Fusion Browser"
#: `manifest.json` içindeki `key` alanından türeyen, yoldan BAĞIMSIZ eklenti kimliği.
#: Eklenti hangi klasörden yüklenirse yüklensin kimliği budur; yerel mesajlaşma
#: izin listesi (`allowed_origins`) bu yüzden uygulama taşınınca bozulmaz.
FIXED_EXTENSION_ID = "dmdljajadkocbomficmpladgajnnidfa"
#: Windows'ta Chrome yerel mesajlaşma bildirimini bu kayıt defteri anahtarından okur.
_WINDOWS_HOST_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"


def chrome_user_data_dir(home: Path | None = None) -> Path:
    """Chrome profillerinin kökü (macOS ve Windows)."""
    kok = home or Path.home()
    if sys.platform == "win32":
        yerel = os.environ.get("LOCALAPPDATA") or str(kok / "AppData" / "Local")
        return Path(yerel) / "Google" / "Chrome" / "User Data"
    return kok / "Library" / "Application Support" / "Google" / "Chrome"


def trusted_extension_dirs() -> list[Path]:
    """Fusion'ın kendi eklenti kopyalarının bulunduğu klasörler (kaynak, paket, kullanıcı)."""
    return [
        Path(__file__).resolve().parents[3] / "chrome-extension",
        Path("/Applications/Fusion.app/Contents/Resources/chrome-extension"),
        base_config_dir() / "chrome-extension",
    ]


def installed_extension_ids(home: Path | None = None) -> set[str]:
    """Chrome profillerinde GÜVENİLİR klasörlerden yüklenmiş eklentilerin kimlikleri.

    Eklentinin adı ya da yolunun `/chrome-extension` ile bitmesi kimlik kanıtı DEĞİLDİR:
    ölçüldü (29 Ekim), aynı adı taşıyan herhangi bir eklenti native host izin listesine
    giriyordu. Gerçek eklentinin kimliğini manifest `key`'i sabitler
    (`FIXED_EXTENSION_ID`); burada yalnız Fusion'ın kendi klasöründen yüklenen kopya
    kabul edilir.
    """
    kok = chrome_user_data_dir(home)
    guvenilir = {_resolved(d) for d in trusted_extension_dirs()}
    kimlikler: set[str] = set()
    for dosya in [*kok.glob("*/Preferences"), *kok.glob("*/Secure Preferences")]:
        try:
            ayarlar = json.loads(dosya.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        uzantilar = ayarlar.get("extensions", {}).get("settings", {}) or {}
        for kimlik, bilgi in uzantilar.items():
            yol = str(bilgi.get("path", "")) if isinstance(bilgi, dict) else ""
            if yol and _resolved(Path(yol)) in guvenilir:
                kimlikler.add(kimlik)
    return kimlikler


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path


def candidate_extension_ids(home: Path | None = None) -> set[str]:
    """Sabit kimlik, güvenilir klasörlerin yol kimlikleri ve oradan yüklenmiş eklentiler."""
    return (
        {FIXED_EXTENSION_ID}
        | {extension_id_for_path(d) for d in trusted_extension_dirs()}
        | installed_extension_ids(home)
    )


def install_native_host(extension_ids: set[str], home: Path | None = None) -> list[Path]:
    """Başlatıcı betiği ve Chrome'un yerel mesajlaşma bildirimini yaz (macOS, Windows).

    `FUSION_NO_NATIVE_HOST` tanımlıysa (testler) hiçbir şey yazılmaz.
    """
    if os.environ.get("FUSION_NO_NATIVE_HOST"):
        return []
    sistem = sys.platform
    if sistem == "darwin" or sistem.startswith("linux"):
        return _write_native_host(extension_ids, home or Path.home())
    if sistem == "win32":
        return _write_native_host_windows(extension_ids)
    return []


def _manifest_body(betik: Path, extension_ids: set[str]) -> dict[str, Any]:
    return {
        "name": HOST_NAME,
        "description": "Fusion Browser yerel eşleşme",
        "path": str(betik),
        "type": "stdio",
        "allowed_origins": sorted(f"chrome-extension://{kimlik}/" for kimlik in extension_ids),
    }


def _write_native_host_windows(extension_ids: set[str]) -> list[Path]:
    """Windows'ta .bat başlatıcı, bildirim dosyası ve HKCU kayıt defteri anahtarı."""
    winreg = importlib.import_module("winreg")  # yalnız Windows'ta var

    betik = base_config_dir() / "chrome-host.bat"
    betik.parent.mkdir(parents=True, exist_ok=True)
    komut = " ".join(f'"{parca}"' for parca in _host_command())
    betik.write_text(f"@echo off\r\n{komut}\r\n", encoding="utf-8")
    hedef = base_config_dir() / f"{HOST_NAME}.json"
    hedef.write_text(json.dumps(_manifest_body(betik, extension_ids), indent=2), encoding="utf-8")
    # Chrome, Chromium, Edge, Brave, Vivaldi, Opera anahtarları (#433).
    for key in windows_host_keys(HOST_NAME):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as anahtar:
            winreg.SetValueEx(anahtar, "", 0, winreg.REG_SZ, str(hedef))
    return [hedef]


def _write_native_host(extension_ids: set[str], home: Path) -> list[Path]:
    """macOS/Linux'ta başlatıcı betiği ve kurulu her tarayıcı dizinine bildirim dosyasını yaz."""
    betik = base_config_dir() / "chrome-host.sh"
    betik.parent.mkdir(parents=True, exist_ok=True)
    komut = " ".join(shlex.quote(parca) for parca in _host_command())
    betik.write_text(f"#!/bin/sh\nexec {komut}\n", encoding="utf-8")
    betik.chmod(0o755)
    bildirim = _manifest_body(betik, extension_ids)
    yazilan: list[Path] = []
    for dizin in _chrome_host_dirs(home):
        if not dizin.parent.is_dir():
            continue  # tarayıcı kurulu değil
        dizin.mkdir(exist_ok=True)
        hedef = dizin / f"{HOST_NAME}.json"
        hedef.write_text(json.dumps(bildirim, indent=2), encoding="utf-8")
        yazilan.append(hedef)
    return yazilan


def main() -> None:
    serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
