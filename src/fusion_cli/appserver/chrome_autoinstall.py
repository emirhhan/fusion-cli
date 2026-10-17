"""Eklentiyi kullanıcı elini sürmeden kurma: macOS erişilebilirlik (System Events) otomasyonu.

Kullanıcı bu yolu açıkça onayladı (Fusion kendi eklentisini kurmak için Chrome'un
`chrome://extensions` sayfasını sürer). Chrome'un resmî yolları kapalıdır (bkz.
docs/CHROME_EKLENTISI_KURULUM.md): markalı Chrome 137+ `--load-extension` bayrağını yok
sayar, uzaktan hata ayıklama varsayılan profilde çalışmaz, `developer_mode` ayarı Secure
Preferences imzasıyla korunur (elle yazmak profili bozar). Geriye kalan, Chrome'un kendi
arayüzünü bir insan gibi sürmektir: Geliştirici modunu açar, "Paketlenmemiş öğe yükle"ye
basar, klasörü seçer. Gereken TEK macOS izni: Fusion'a Erişilebilirlik.

Kapsam yalnız `chrome://extensions`; profil dosyalarına yazılmaz, çerez/oturum okunmaz.
Arayüz değişirse adım başarısız olur ve akış elle kuruluma düşer (sayfa zaten açıktır).
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config.paths import base_config_dir
from .chrome_install import _platform, begin_install, install_status

ACCESSIBILITY_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
#: Arayüz adımlarının (sayfa yükleme, diyalog) toplam üst sınırı.
SCRIPT_TIMEOUT_SECONDS = 240
#: Arayüz adımından sonra eklentinin profilde görünmesini beklemek için üst sınır.
VERIFY_WAIT_SECONDS = 30.0
VERIFY_POLL_SECONDS = 1.0

# Düğme adları Chrome diline göre değişir; ikisi de aranır.
_APPLESCRIPT = r"""
property dumpText : ""

-- Tek geçiş: her öğenin rolü/adı/açıklaması BİR kez okunur (öğe başına üç soru).
-- Aynı geçişte hem eşleşme aranır hem tanı metni biriktirilir; eşleşme çıkarsa hemen döner.
on findElement(wordList)
  set my dumpText to ""
  tell application "System Events"
    tell process "Google Chrome"
      repeat 3 times
        set my dumpText to ""
        try
          set n to 0
          repeat with el in (entire contents of front window)
            set n to n + 1
            if n > 600 then exit repeat
            set r to ""
            set t to ""
            set d to ""
            try
              set r to (role of el) as text
            end try
            try
              set t to (title of el) as text
            end try
            try
              set d to (description of el) as text
            end try
            set my dumpText to my dumpText & r & " | " & t & " | " & d & linefeed
            repeat with w in wordList
              if t contains (w as text) or d contains (w as text) then return el
            end repeat
          end repeat
        on error errText
          set my dumpText to my dumpText & "tarama-hatasi: " & errText & linefeed
        end try
        delay 2
      end repeat
    end tell
  end tell
  return missing value
end findElement

on writeDump(pathText)
  try
    do shell script "printf %s " & quoted form of (my dumpText) & " > " & quoted form of pathText
  end try
end writeDump

on run argv
  set extPath to item 1 of argv
  set axPath to item 2 of argv
  tell application "Google Chrome"
    activate
    if (count of windows) = 0 then make new window
    tell front window to make new tab with properties {URL:"chrome://extensions"}
  end tell
  delay 2
  tell application "System Events"
    tell process "Google Chrome"
      try
        set value of attribute "AXManualAccessibility" to true
      end try
      try
        set value of attribute "AXEnhancedUserInterface" to true
      end try
    end tell
  end tell
  delay 3
  set devSwitch to my findElement({"Developer mode", "Geliştirici modu"})
  if devSwitch is missing value then
    my writeDump(axPath)
    return "no-switch"
  end if
  tell application "System Events"
    try
      set switchState to value of attribute "AXValue" of devSwitch
      if switchState is 0 or switchState is false then click devSwitch
    on error
      click devSwitch
    end try
  end tell
  delay 1
  set loadButton to my findElement({"Load unpacked", "Paketlenmemiş öğe yükle"})
  if loadButton is missing value then
    my writeDump(axPath)
    return "no-load-button"
  end if
  tell application "System Events"
    click loadButton
    delay 1.2
    keystroke "g" using {command down, shift down}
    delay 0.8
    keystroke extPath
    delay 0.5
    key code 36
    delay 1
    key code 36
  end tell
  return "ok"
end run
"""

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _osascript(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=SCRIPT_TIMEOUT_SECONDS,
    )


def accessibility_granted(runner: Runner = _osascript) -> bool:
    """macOS, Fusion'ın başka uygulamanın arayüzünü sürmesine izin vermiş mi."""
    cevap = runner(
        ["osascript", "-e", 'tell application "System Events" to get UI elements enabled']
    )
    return cevap.returncode == 0 and cevap.stdout.strip() == "true"


def drive_chrome_ui(extension_dir: Path, runner: Runner = _osascript) -> str:
    """Arayüz betiğini çalıştır; "ok", "no-switch", "no-load-button" ya da "error"."""
    betik = base_config_dir() / "chrome-install.applescript"
    betik.parent.mkdir(parents=True, exist_ok=True)
    betik.write_text(_APPLESCRIPT, encoding="utf-8")
    tanilama = base_config_dir() / "chrome-install-ax.txt"
    try:
        cevap = runner(["osascript", str(betik), str(extension_dir), str(tanilama)])
    except subprocess.TimeoutExpired:
        return f"zaman-asimi: betik {SCRIPT_TIMEOUT_SECONDS} sn içinde bitmedi"
    if cevap.returncode != 0:
        # Neden görünür olsun: "error" tek başına izin mi, zaman aşımı mı, arayüz mü söylemiyordu.
        neden = " ".join(cevap.stderr.split())[:160]
        if "-1743" in cevap.stderr or "not allowed" in cevap.stderr.lower():
            return (
                "otomasyon-izni-yok: Sistem Ayarları > Gizlilik ve Güvenlik > Otomasyon'da "
                "Fusion'ın Chrome'u denetlemesine izin ver"
            )
        return f"error: {neden}" if neden else "error"
    return cevap.stdout.strip() or "error"


def wait_until_installed(
    home: Path | None = None, sleep: Callable[[float], None] = time.sleep
) -> bool:
    bitis = time.monotonic() + VERIFY_WAIT_SECONDS
    while time.monotonic() < bitis:
        if install_status(home)["eklenti_yuklu"]:
            return True
        sleep(VERIFY_POLL_SECONDS)
    return bool(install_status(home)["eklenti_yuklu"])


def auto_install(
    home: Path | None = None,
    runner: Runner = _osascript,
    prepare: Callable[..., dict[str, Any]] = begin_install,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Hazırla, izin varsa arayüzü sür, sonucu doğrula.

    `asama`: "yuklendi" | "izin_gerekli" | "elle" | "desteklenmiyor" | "hata".
    """
    if _platform() != "darwin":
        return {**prepare(home=home), "asama": "desteklenmiyor"}
    if install_status(home)["eklenti_yuklu"]:
        return {"ok": True, "asama": "yuklendi", **install_status(home)}
    hazir = prepare(home=home)  # kopyalar, yerel mesajlaşmayı yazar, sayfayı açar
    if not hazir["ok"]:
        return {**hazir, "asama": "hata"}
    if not accessibility_granted(runner):
        runner(["open", ACCESSIBILITY_PANE])
        return {
            **hazir,
            "asama": "izin_gerekli",
            "metin": (
                "Sistem Ayarları > Gizlilik ve Güvenlik > Erişilebilirlik'te Fusion'ı aç; "
                "sonra Eklentiyi kur'a yeniden bas. Bu tek izindir."
            ),
        }
    sonuc = drive_chrome_ui(Path(hazir["yol"]), runner)
    if sonuc == "ok" and wait_until_installed(home, sleep):
        return {"ok": True, "asama": "yuklendi", "yol": hazir["yol"], **install_status(home)}
    return {
        **hazir,
        "asama": "elle",
        "metin": f"{_manual_message(sonuc)} Tanı: {base_config_dir() / 'chrome-install-ax.txt'}",
    }


def _manual_message(result: str) -> str:
    """Otomatik adım neden bitmedi ve elle ne yapılır (açılan sayfada tek tık)."""
    if result == "error":
        return (
            "Fusion Chrome'u süremedi. Sistem Ayarları > Gizlilik ve Güvenlik > Otomasyon'da "
            "Fusion için Google Chrome ve System Events'i aç, sonra Eklentiyi kur'a yeniden bas; "
            "ya da açılan sayfada Geliştirici modu > Paketlenmemiş öğe yükle ile panodaki "
            "klasörü seç."
        )
    return (
        "Chrome'un sayfa düzeni beklenenden farklı; otomatik adım bitmedi. Açılan sayfada "
        "Geliştirici modu > Paketlenmemiş öğe yükle ile panodaki klasörü seç."
    )


async def auto_install_async() -> dict[str, Any]:
    return await asyncio.to_thread(auto_install)
