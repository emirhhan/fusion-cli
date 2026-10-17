"""Fusion Browser eklentisinin kurulum yardımcısı (Ayarlar > Tarayıcı, `fusion chrome-kur`).

Chrome kullanıcının onayı olmadan eklenti yüklemeyi bilerek engeller; bu yüzden
kurulum "tam otomatik" değil, TEK ONAYLI bir akıştır. Fusion'ın yaptığı kısım:

1. Eklenti dosyalarını kalıcı bir klasöre kopyalar (uygulama taşınsa bile yol sabit).
2. Chrome'un yerel mesajlaşma kaydını (eklentinin Fusion'ı bulması) yazar.
3. `chrome://extensions` sayfasını açar, klasör yolunu panoya koyar ve klasörü gösterir.
4. Sonucu doğrular: eklenti Chrome profillerinde yüklü ve etkin mi, Fusion'la
   el sıkıştı mı (köprü `bagli`).

Kullanıcının yaptığı kısım: Geliştirici modunu açıp "Paketlenmemiş öğe yükle" ile
klasörü seçmek (ya da klasörü sayfaya sürüklemek). Belge: docs/CHROME_EKLENTISI_KURULUM.md.
Çerezlere, oturumlara ya da Chrome profil verisine yazılmaz; yalnız okunur.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config.paths import base_config_dir
from .chrome_host import (
    EXTENSION_NAME,
    FIXED_EXTENSION_ID,
    candidate_extension_ids,
    chrome_user_data_dir,
    install_native_host,
)

EXTENSIONS_URL = "chrome://extensions"
#: Kopyalanmayan geliştirme artıkları.
_IGNORED = shutil.ignore_patterns(".DS_Store", "*.map", "__pycache__")

Runner = Callable[[list[str], str | None], None]


def source_extension_dir() -> Path | None:
    """Kaynak ağaçtaki ya da kurulu uygulamadaki eklenti klasörü."""
    adaylar = [
        Path(__file__).resolve().parents[3] / "chrome-extension",
        Path("/Applications/Fusion.app/Contents/Resources/chrome-extension"),
        Path(sys.executable).resolve().parent / "chrome-extension",
    ]
    return next((yol for yol in adaylar if (yol / "manifest.json").is_file()), None)


def stable_extension_dir() -> Path:
    return base_config_dir() / "chrome-extension"


def stage_extension() -> Path:
    """Eklentiyi kalıcı klasöre eşitle ve yolunu ver; kaynak yoksa FileNotFoundError."""
    kaynak = source_extension_dir()
    if kaynak is None:
        raise FileNotFoundError("Fusion Browser eklenti klasörü bulunamadı.")
    hedef = stable_extension_dir()
    if hedef.exists():
        shutil.rmtree(hedef)
    shutil.copytree(kaynak, hedef, ignore=_IGNORED)
    return hedef


def extension_state(home: Path | None = None) -> dict[str, Any]:
    """Chrome profillerinde Fusion Browser'ın yüklü/etkin olup olmadığı (yalnız okur)."""
    kok = chrome_user_data_dir(home)
    bulundu: dict[str, Any] = {"yuklu": False, "etkin": False, "kimlik": None, "surum": None}
    for dosya in [*kok.glob("*/Preferences"), *kok.glob("*/Secure Preferences")]:
        try:
            ayarlar = json.loads(dosya.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        uzantilar = ayarlar.get("extensions", {}).get("settings", {}) or {}
        for kimlik, bilgi in uzantilar.items():
            if not isinstance(bilgi, dict):
                continue
            manifest = bilgi.get("manifest") or {}
            if manifest.get("name") != EXTENSION_NAME and kimlik != FIXED_EXTENSION_ID:
                continue
            etkin = bilgi.get("state", 1) == 1 and not bilgi.get("disable_reasons")
            if not bulundu["yuklu"] or (etkin and not bulundu["etkin"]):
                bulundu = {
                    "yuklu": True,
                    "etkin": etkin,
                    "kimlik": kimlik,
                    "surum": manifest.get("version"),
                }
    return bulundu


def _run(command: list[str], stdin: str | None = None) -> None:
    subprocess.run(
        command,
        input=stdin,
        text=True,
        check=False,
        timeout=15,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _platform() -> str:
    # `sys.platform` doğrudan karşılaştırılırsa mypy tek sistemi görür; testler de değiştirebilsin.
    return sys.platform


def _platform_commands(folder: Path) -> list[tuple[list[str], str | None]]:
    yol = str(folder)
    sistem = _platform()
    if sistem == "darwin":
        return [
            (["pbcopy"], yol),
            (["open", "-a", "Google Chrome", EXTENSIONS_URL], None),
            (["open", yol], None),
        ]
    if sistem == "win32":
        return [
            (["clip"], yol),
            (["cmd", "/c", "start", "", "chrome", EXTENSIONS_URL], None),
            (["explorer", yol], None),
        ]
    return []


def begin_install(runner: Runner = _run, home: Path | None = None) -> dict[str, Any]:
    """Kurulumu hazırla ve Chrome'u onay adımına getir; sonucu `durum` ile doğrula."""
    if _platform() not in {"darwin", "win32"}:
        return {"ok": False, "metin": "Otomatik kurulum yalnız macOS ve Windows'ta desteklenir."}
    try:
        klasor = stage_extension()
    except (FileNotFoundError, OSError) as cause:
        return {"ok": False, "metin": f"Eklenti hazırlanamadı: {cause}"}
    try:
        install_native_host(candidate_extension_ids(home), home)
    except OSError as cause:
        return {"ok": False, "metin": f"Chrome eşleşme kaydı yazılamadı: {cause}"}
    for command, stdin in _platform_commands(klasor):
        try:
            runner(command, stdin)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "metin": "Chrome açılamadı; Chrome kurulu mu?"}
    return {"ok": True, "yol": str(klasor), "adimlar": install_steps(), **install_status(home)}


def install_steps() -> list[str]:
    return [
        "Açılan chrome://extensions sayfasında sağ üstteki “Geliştirici modu”nu aç.",
        "“Paketlenmemiş öğe yükle”ye bas; klasör penceresinde Cmd+Shift+G (Windows: Ctrl+V) "
        "ile panodaki yolu yapıştır ya da klasörü sayfaya sürükle.",
        "Fusion Browser simgesine bir kez tıklayıp “Chrome iznini iste”yi onayla.",
    ]


def install_status(home: Path | None = None) -> dict[str, Any]:
    """Ayarlar ekranının doğruladığı iki bilgi: yüklü/etkin mi; el sıkışma ayrı (köprü)."""
    durum = extension_state(home)
    return {
        "eklenti_yuklu": durum["yuklu"],
        "eklenti_etkin": durum["etkin"],
        "eklenti_surum": durum["surum"],
    }
