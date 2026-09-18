"""Tur penceresini kullanıcının ekranından uzak tutmak (yalnız macOS).

Ölçüldü (17 Eylül): ChatGPT web oturumu GÖRÜNMEZ (headless) Chrome'da Cloudflare
"Bir dakika lütfen" doğrulamasına takıldı ve yedi turun yedisi düştü; kullanıcı
doğrulamayı görünür tarayıcıda geçse bile headless kipte yine takıldı. Aynı profil
`headless: false` ile açıldığında ChatGPT ilk turda sorunsuz çalıştı. Görünür kipin
bedeli ise kullanıcının önünde açılan penceredir: Chrome `--window-position` bayrağını
da CDP'nin pencere konumu çağrısını da yok sayar.

Çözüm ölçüldü ve çalıştı: Chrome normal (headed) başlatılır, hemen ardından macOS'ta
SÜRECİ gizleriz — System Events ile `set visible ... to false`, yani Cmd+H ile birebir
aynı işlem. Pencere ekranda hiç görünmez, sayfa çalışmaya devam eder (ölçüldü: mesaj
gönderildi, yanıt 4,2 saniyede geldi).

Bu bir bot koruması atlatma tekniği DEĞİLDİR: tarayıcı normal Chrome'dur, parmak izi
ve sunucuya giden hiçbir şey değişmez; yapılan tek şey pencereyi kullanıcının
ekranından uzak tutmaktır.

Gizleme "en iyi çaba"dır: System Events için Otomasyon izni verilmemişse çağrı
başarısız olur. Bu durumda tur DÜŞMEZ, pencere görünür kalır; neden log'a yazılır
VE kullanıcıya gösterilecek Türkçe bir açıklama sonuç nesnesiyle döner — sessizce
yutulmaz (bkz. `WindowHideResult`).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

#: Chrome'un profil dizinine yazdığı kilit. Sembolik bağın adı "<makine>-<pid>".
SINGLETON_LOCK_FILE = "SingletonLock"

#: Gizleme betiği. Süreç ADIYLA değil `unix id` ile hedeflenir: kullanıcının kendi
#: Chrome'u da "Google Chrome" adını taşır ve ada göre gizleme onu da kapatırdı.
HIDE_SCRIPT_TEMPLATE = (
    'tell application "System Events" to set visible of '
    "(first process whose unix id is {pid}) to false"
)

#: `osascript` çağrısının üst süre sınırı. Yerel bir Apple Event'tir ve milisaniyeler
#: sürer; sınır yalnız yanıt vermeyen System Events'in turu bloklamasını engeller.
HIDE_TIMEOUT_S = 5.0

#: Chrome'un kilit dosyasını yazması için beklenecek süre. Çağrı hata ayıklama portu
#: yazıldıktan sonra yapılır, kilit o noktada neredeyse her zaman hazırdır; kısa
#: bekleme yalnız yarış durumunu kapatır.
PID_WAIT_S = 2.0
PID_POLL_INTERVAL_S = 0.1


#: Kullanıcıya gösterilen metinler. Pencere görünür kaldıysa kullanıcı bunu zaten
#: görür; metin NEDENİNİ ve ne yapacağını söyler.
HIDE_FAILED_MESSAGE = (
    "Fusion'ın tarayıcı penceresi gizlenemedi, bu yüzden ekranında görünüyor. "
    "Büyük olasılıkla macOS izni eksik: Sistem Ayarları > Gizlilik ve Güvenlik > "
    "Otomasyon altında Fusion'ı (ya da onu çalıştıran terminali) System Events için "
    "etkinleştir; gerekirse Erişilebilirlik listesine de ekle. Pencereyi Cmd+H ile "
    "elle de gizleyebilirsin — sohbet çalışmaya devam eder."
)
PID_UNKNOWN_MESSAGE = (
    "Fusion'ın tarayıcı penceresi gizlenemedi: Chrome süreci bulunamadı. Pencere "
    "görünüyorsa Cmd+H ile gizleyebilirsin; sorun sürerse web oturumunu yeniden başlat."
)
UNSUPPORTED_MESSAGE = (
    "Gizli pencere kipi yalnız macOS'ta var. Bu bilgisayarda tarayıcı görünmez "
    "(headless) kipte açıldı; ChatGPT doğrulamaya takılırsa görünür kipi seç."
)


@dataclass(frozen=True, slots=True)
class WindowHideResult:
    """Pencere gizleme denemesinin sonucu.

    Başarısızlık beklenen bir durumdur (izin yok, süreç bulunamadı) ve exception
    ile değil bu nesneyle taşınır; `message` kullanıcıya gösterilecek Türkçe metindir.
    """

    is_hidden: bool
    message: str = ""


def supports_window_hiding() -> bool:
    """Bu platformda pencere işletim sistemi düzeyinde gizlenebilir mi?"""
    return sys.platform == "darwin"


def profile_process_id(profile: Path) -> int | None:
    """Profili tutan Chrome sürecinin kimliği; okunamıyorsa None."""
    try:
        owner = (profile / SINGLETON_LOCK_FILE).readlink().name
        pid = int(owner.rsplit("-", 1)[-1])
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


async def hide_profile_window(profile: Path) -> WindowHideResult:
    """Profilin Chrome penceresini kullanıcının ekranından gizle.

    Hiçbir koşulda hata fırlatmaz: gizleme başarısız olsa bile tur devam eder,
    neden sonuç nesnesinde döner.
    """
    if not supports_window_hiding():
        return WindowHideResult(is_hidden=False, message=UNSUPPORTED_MESSAGE)
    pid = await _wait_profile_process_id(profile)
    if pid is None:
        _logger.warning("Chrome süreç kimliği okunamadı; pencere gizlenemedi (profil=%s)", profile)
        return WindowHideResult(is_hidden=False, message=PID_UNKNOWN_MESSAGE)
    return await _hide_process(pid)


async def _wait_profile_process_id(profile: Path) -> int | None:
    """Kilit dosyası yazılana kadar kısa süre bekleyerek süreç kimliğini oku."""
    deadline = time.monotonic() + PID_WAIT_S
    while True:
        pid = profile_process_id(profile)
        if pid is not None or time.monotonic() >= deadline:
            return pid
        await asyncio.sleep(PID_POLL_INTERVAL_S)


async def _hide_process(pid: int) -> WindowHideResult:
    """Süreci Cmd+H ile aynı şekilde gizle; başarısızlığı log'la ve sonuçla bildir."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", HIDE_SCRIPT_TEMPLATE.format(pid=pid)],
            capture_output=True,
            text=True,
            timeout=HIDE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _logger.warning("Tarayıcı penceresi gizlenemedi (pid=%s): %s", pid, error)
        return WindowHideResult(is_hidden=False, message=HIDE_FAILED_MESSAGE)
    if result.returncode != 0:
        _logger.warning(
            "Tarayıcı penceresi gizlenemedi (pid=%s, kod=%s): %s",
            pid,
            result.returncode,
            result.stderr.strip(),
        )
        return WindowHideResult(is_hidden=False, message=HIDE_FAILED_MESSAGE)
    return WindowHideResult(is_hidden=True)
