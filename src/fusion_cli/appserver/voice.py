"""Sesli yanıt: Fusion'ın kullanıcıyla konuşması.

Tasarım kararı — BEDAVA ve ÇEVRİMDIŞI: işletim sisteminin kendi sentezleyicisi
kullanılır. macOS'ta `say`, Windows'ta PowerShell'in `System.Speech` sınıfı.
Model indirilmez, API anahtarı istenmez, ağa çıkılmaz. Kullanıcının kotası ve
gizliliği bu yüzden hiç etkilenmez: konuşulan metin bilgisayardan çıkmaz.

Türkçe uyumu ölçüldü: macOS'ta `Yelda tr_TR` sesi kuruludur.
"""

from __future__ import annotations

import contextlib
import platform
import shutil
import subprocess
from typing import Any

#: Sentezleyiciye verilecek metnin üst sınırı. Uzun cevabın tamamını okumak
#: kullanıcıyı bekletir; arayüz gerekiyorsa parça parça gönderir.
MAX_SPEECH_CHARS = 4_000


#: Apple'ın ücretsiz indirilebilen yüksek kaliteli Türkçe sesi. Sistemde
#: varsayılan olarak YALNIZ `voice.compact.tr-TR.Yelda` kurulu gelir ve o
#: kademe belirgin biçimde robotik duyulur (kullanıcı bildirdi, ölçüldü).
#: Katalogda doğrulandı: `com.apple.ttsbundle.Cem`, tr-TR, 120 MB, ücretsiz.
BETTER_TURKISH_VOICE = "Cem"

#: Kalite işaretleri, iyiden kötüye. `compact` Apple'ın en düşük kademesidir
#: ve belirgin biçimde robotik duyulur; yalnız başka seçenek yokken kullanılır.
_QUALITY_ORDER = ("premium", "ttsbundle", "enhanced", "compact")

#: Kalite işareti hiç görünmeyen ses için varsayılan sıra. `say -v ?` kalite
#: bilgisi vermediğinden çoğu ses buraya düşer; compact'ten kötü sayılmaz.
_UNKNOWN_RANK = _QUALITY_ORDER.index("compact")


def _quality_rank(identifier: str) -> int:
    lowered = identifier.casefold()
    for index, marker in enumerate(_QUALITY_ORDER):
        if marker in lowered:
            return index
    return _UNKNOWN_RANK


def best_voice(installed: tuple[tuple[str, str, str], ...]) -> str | None:
    """Kurulu Türkçe sesler arasından KALİTECE en iyisini seç.

    Girdi `(ad, dil, kimlik)` üçlüleridir. İlk bulunanı almak yanlış olurdu:
    sistemde hem compact hem yüksek kaliteli ses kuruluysa kullanıcı iyi olanı
    duymalı.
    """
    turkish = [item for item in installed if item[1].casefold().startswith("tr")]
    if not turkish:
        return None
    # Eşit kalitede ada göre bilinen tercih uygulanır: iki compact ses arasında
    # Cem, Yelda'dan belirgin biçimde daha doğal duyuluyor (dinlenerek seçildi).
    tercih = {"cem": 0, "yelda": 1}
    return min(
        turkish,
        key=lambda item: (_quality_rank(item[2]), tercih.get(item[0].casefold(), 2)),
    )[0]


def upgrade_hint(installed: tuple[tuple[str, str, str], ...]) -> str | None:
    """Daha iyi bir Türkçe ses kurulabiliyorsa kullanıcıya söylenecek metin.

    Daha iyisi varken sessizce kötüsüyle konuşmak, kullanıcının Fusion'ı
    olduğundan kötü sanmasına yol açar.
    """
    turkish = [item for item in installed if item[1].casefold().startswith("tr")]
    if not turkish:
        return None
    if any(_quality_rank(item[2]) < _QUALITY_ORDER.index("compact") for item in turkish):
        return None
    return (
        f"Daha doğal bir Türkçe ses ücretsiz indirilebilir: {BETTER_TURKISH_VOICE}. "
        "Sistem Ayarları → Erişilebilirlik → Sözlü İçerik → Sistem Sesi → "
        "Sesleri Yönet → Türkçe yolundan kurabilirsin."
    )


#: Piper sentez parametreleri. Değerler UYDURULMADI: aynı cümle üç farklı hızda
#: dinlenerek seçildi ve kullanıcı "biraz hızlandıralım, robotik olsa da olur"
#: dedi. Bu yüzden `length_scale` 1.0'ın altında — varsayılandan hızlı.
PIPER_DEFAULTS: dict[str, float] = {
    "length_scale": 0.92,
    # Hece süresi değişkenliği: mekanik tınıyı azaltan asıl ayar.
    "noise_w_scale": 0.9,
    "sentence_silence": 0.25,
}

#: Piper'ın Türkçe modeli. Katalogda doğrulandı: tek Türkçe ses budur
#: (`fahrettin` ve `fettah` 404 veriyor). MIT lisanslı, 60 MB, çevrimdışı.
PIPER_TURKISH_MODEL = "tr_TR-dfki-medium"


def piper_argv(model: str, output: str, settings: dict[str, float]) -> list[str]:
    """Piper'ı çalıştıracak komutu üret."""
    return [
        "piper",
        "-m",
        model,
        "-f",
        output,
        "--length-scale",
        str(settings["length_scale"]),
        "--noise-w-scale",
        str(settings["noise_w_scale"]),
        "--sentence-silence",
        str(settings["sentence_silence"]),
    ]


def engine_for(
    *, piper_model: str | None, system_voice: str | None
) -> tuple[str | None, str | None]:
    """Hangi motorun kullanılacağını ve gerekiyorsa sebebini döndür.

    Piper varsa o tercih edilir: sistem sesinden daha doğal ve Windows'ta da
    çalışır. Model indirilmemişse sistem sesine düşülür ama SEBEBİ söylenir —
    sessizce daha kötü sesle konuşmak kullanıcıyı yanıltır.
    """
    if piper_model:
        return "piper", None
    if system_voice:
        return "sistem", (
            "Daha doğal ses için Piper modeli indirilmedi; şimdilik sistem sesi kullanılıyor."
        )
    return None, "Bu bilgisayarda kullanılabilir bir Türkçe ses yok."


def turkish_voice(installed: tuple[str, ...]) -> str | None:
    """Kurulu sesler arasından Türkçe olanın adını döndür.

    Ses adı UYDURULMAZ: sistemde gerçekten kurulu olanlardan seçilir. Türkçe ses
    yoksa None döner ve çağıran varsayılan sesle devam eder — sessizce yanlış
    dilde okumaktansa sistem varsayılanı doğrudur.
    """
    for line in installed:
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("tr_"):
            return parts[0]
    return None


def installed_voice_records() -> tuple[tuple[str, str, str], ...]:
    """Kurulu sesleri `(ad, dil, kimlik)` olarak listele.

    Kimlik kalite kademesini taşır (`compact`, `ttsbundle`, `premium`); seçim
    bu yüzden ada değil kimliğe bakar.
    """
    if platform.system() != "Darwin" or shutil.which("say") is None:
        return ()
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    records: list[tuple[str, str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        locale = parts[1].replace("_", "-")
        # `say -v ?` KALİTE bilgisi vermez. Kimliği uydurmak yanlış olurdu:
        # yüksek kaliteli bir ses kurulduğunda onu "compact" diye etiketler ve
        # sıralama sessizce yanlış sesi seçerdi. Bu yüzden kimlik alanına
        # yalnız `say`in gerçekten söylediği ad yazılır; kalite ipucu varsa
        # (macOS bazı sesleri "Cem (Enhanced)" gibi listeler) addan okunur.
        records.append((parts[0], locale, line.split("#")[0].strip()))
    return tuple(records)


def installed_voices() -> tuple[str, ...]:
    """macOS'ta kurulu sesleri listele; başka platformda boş döner."""
    if platform.system() != "Darwin" or shutil.which("say") is None:
        return ()
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def speak_argv(system: str, text: str, *, voice: str | None) -> list[str]:
    """Metni seslendirecek komutu üret.

    Metin TEK argüman olarak geçer ve kabuktan geçirilmez: seslendirilecek metin
    modelden ya da kullanıcıdan gelir, kabuk kaçışına asla güvenilmez.
    """
    name = system.casefold()
    if name == "darwin":
        argv = ["say"]
        if voice:
            argv += ["-v", voice]
        return [*argv, text]
    if name == "windows":
        # PowerShell tek satırlık betiği argüman olarak alır; metin betiğin
        # içine tek tırnakla ve kendi tırnağı ikilenerek gömülür.
        güvenli = text.replace("'", "''")
        betik = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak('{güvenli}')"
        )
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", betik]
    raise ValueError(f"Sesli yanıt bu platformda desteklenmiyor: {system}")


def speak(text: object) -> dict[str, Any]:
    """`ses.konus`: metni sistem sesiyle oku.

    Süreç BEKLENMEZ: uzun bir cevabı okurken arayüz donmamalı. Konuşmayı
    durdurmak `ses.durdur` ile yapılır.
    """
    from .voice_text import prepare_speech

    # Ham cevap seslendirilmez: markdown, kod bloğu, dosya yolu ve sayılar
    # önce okunabilir hâle getirilir (bkz. `voice_text`). Bu katman olmadan
    # hangi model kullanılırsa kullanılsın sonuç kötü duyulur.
    content = prepare_speech(str(text or ""))
    if not content:
        return {"ok": False, "metin": "Okunacak metin boş."}
    voice = best_voice(installed_voice_records())
    try:
        argv = speak_argv(platform.system(), content, voice=voice)
    except ValueError as error:
        return {"ok": False, "metin": str(error)}
    try:
        process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        return {"ok": False, "metin": f"Sesli yanıt başlatılamadı: {error}"}
    return {"ok": True, "pid": process.pid, "ses": voice}


def stop() -> dict[str, Any]:
    """`ses.durdur`: süren konuşmayı kes."""
    name = platform.system().casefold()
    argv = ["killall", "say"] if name == "darwin" else ["taskkill", "/IM", "powershell.exe", "/F"]
    # Konuşacak süreç yoksa bu bir hata değildir; durdurma yine başarılıdır.
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(argv, capture_output=True, check=False, timeout=10)
    return {"ok": True}


def status() -> dict[str, Any]:
    """`ses.durum`: sesli yanıt kullanılabilir mi, hangi sesle ve daha iyisi var mı?"""
    records = installed_voice_records()
    voice = best_voice(records)
    supported = platform.system().casefold() in ("darwin", "windows")
    return {
        "ok": True,
        "kullanilabilir": supported,
        "ses": voice,
        "turkce": voice is not None,
        # Daha iyisi kurulabiliyorsa SÖYLENİR; sessizce kötüsüyle konuşulmaz.
        "yukseltme": upgrade_hint(records),
    }
