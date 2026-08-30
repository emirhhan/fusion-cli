"""Sesli yanıt: Fusion'ın kullanıcıyla konuşması.

Tasarım kararı — BEDAVA ve ÇEVRİMDIŞI: işletim sisteminin kendi sentezleyicisi
kullanılır. macOS'ta `say`, Windows'ta PowerShell'in `System.Speech` sınıfı.
Model indirilmez, API anahtarı istenmez, ağa çıkılmaz. Kullanıcının kotası ve
gizliliği bu yüzden hiç etkilenmez: konuşulan metin bilgisayardan çıkmaz.

Türkçe uyumu ölçüldü: macOS'ta `Yelda tr_TR` sesi kuruludur.
"""

from __future__ import annotations

import contextlib
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
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


def _data_home() -> Path:
    """Kullanıcı verisinin kökü. Platforma göre değişir."""
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Fusion"
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Fusion"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "fusion"


def piper_model_path() -> Path:
    """İndirilen Piper modelinin yolu.

    Model uygulama PAKETİNE yazılmaz: paket imzasını bozar ve her güncellemede
    silinir. Kullanıcı veri dizini güncellemeden etkilenmez.
    """
    return _data_home() / "voices" / f"{PIPER_TURKISH_MODEL}.onnx"


def piper_download_urls() -> tuple[str, str]:
    """Model ve yapılandırma dosyasının indirme adresleri.

    Kaynak, Piper'ın resmî ses deposudur. Adres elle kurulmaz; katalogdaki
    dizin düzeni sabittir (`<dil>/<yerel>/<ses>/<kalite>`).
    """
    taban = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "tr/tr_TR/dfki/medium/tr_TR-dfki-medium"
    )
    return f"{taban}.onnx", f"{taban}.onnx.json"


def _open_url(url: str) -> Any:  # noqa: ANN401 — urlopen'ın dönüşü tiplenmemiş
    """Adresi aç. Testler bunu değiştirir; ağa gerçekten çıkılmaz."""
    from urllib.request import urlopen

    return urlopen(url, timeout=60)


def download_piper_model(progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Türkçe Piper modelini indir.

    İndirme SESSİZ olmaz: 60 MB'lık dosyada kullanıcı ilerlemeyi görmeli.
    Yarım kalan dosya "kurulu" sanılırsa Piper her açılışta çöker; bu yüzden
    önce geçici ada yazılır ve ancak tamamlanınca yerine taşınır.
    """
    hedef = piper_model_path()
    if hedef.is_file():
        return {"ok": True, "zaten": True, "yol": str(hedef)}
    hedef.parent.mkdir(parents=True, exist_ok=True)
    onnx_url, config_url = piper_download_urls()

    gecici = hedef.with_suffix(".onnx.indiriliyor")
    try:
        with _open_url(onnx_url) as yanit:
            toplam = int(yanit.headers.get("Content-Length") or 0)
            inen = 0
            with gecici.open("wb") as akis:
                while True:
                    parca = yanit.read(1024 * 256)
                    if not parca:
                        break
                    akis.write(parca)
                    inen += len(parca)
                    progress({"inen": inen, "toplam": toplam or inen})
        with _open_url(config_url) as yanit:
            hedef.with_suffix(".onnx.json").write_bytes(yanit.read())
    except Exception as error:  # ağ, disk, kesinti
        gecici.unlink(missing_ok=True)
        return {"ok": False, "metin": f"Ses modeli indirilemedi: {error}"}

    gecici.replace(hedef)
    return {"ok": True, "zaten": False, "yol": str(hedef)}


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


def _speak_with_piper(text: str, model: Path) -> dict[str, Any]:
    """Metni Piper ile seslendirip çal.

    Piper ses dosyası üretir, çalmayı işletim sistemine bırakırız. İki adımı
    tek boruya bağlamak yerine geçici dosya kullanılır: Piper'ın çıktısı WAV
    başlığı taşır ve akış hâlinde çalmak platforma göre değişirdi.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as gecici:
        cikti = Path(gecici.name)
    argv = [
        sys.executable,
        "-m",
        "piper",
        "-m",
        str(model),
        "-f",
        str(cikti),
        "--length-scale",
        str(PIPER_DEFAULTS["length_scale"]),
        "--noise-w-scale",
        str(PIPER_DEFAULTS["noise_w_scale"]),
        "--sentence-silence",
        str(PIPER_DEFAULTS["sentence_silence"]),
    ]
    if getattr(sys, "frozen", False):
        # Paketlenmiş ikilide `-m` yoktur; kendi alt komutu kullanılır.
        argv = [sys.executable, "piper-say", str(model), str(cikti)]
    try:
        subprocess.run(argv, input=text, text=True, capture_output=True, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        cikti.unlink(missing_ok=True)
        return {"ok": False, "metin": f"Ses üretilemedi: {error}"}

    calar = (
        ["afplay", str(cikti)]
        if platform.system() == "Darwin"
        else [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(New-Object Media.SoundPlayer '{cikti}').PlaySync()",
        ]
    )
    try:
        process = subprocess.Popen(calar, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        return {"ok": False, "metin": f"Ses çalınamadı: {error}"}
    return {"ok": True, "pid": process.pid, "motor": "piper"}


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
    # Piper modeli indirilmişse o tercih edilir: sistem sesleri Türkçe'de
    # compact kademede kalıyor ve Windows'ta Türkçe ses hiç yok.
    model = piper_model_path()
    if model.is_file():
        return _speak_with_piper(content, model)

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
    """`ses.durum`: hangi motor, hangi ses ve gerçekten uygulanabilir bir öneri var mı?

    Öneri KOŞULLUDUR. Daha önce burada bir hata vardı: Cem zaten kuruluyken ve
    motor Piper'ken bile "Cem'i indir" deniyordu. Kurulu olanı önermek
    kullanıcıyı yanıltır; öneri yalnız gerçekten işe yarayacaksa çıkar.
    """
    records = installed_voice_records()
    system_voice = best_voice(records)
    model = piper_model_path()
    piper_ready = model.is_file()
    supported = piper_ready or platform.system().casefold() in ("darwin", "windows")

    if piper_ready:
        # Piper devredeyken sistem sesi önerisi anlamsızdır.
        hint: str | None = None
    elif system_voice:
        hint = upgrade_hint(records)
    else:
        hint = (
            "Türkçe ses bulunamadı. Ayarlar'dan Fusion'ın kendi ses modelini "
            "indirerek konuşmayı açabilirsin."
        )

    return {
        "ok": True,
        "kullanilabilir": supported,
        "motor": "piper" if piper_ready else "sistem",
        "ses": PIPER_TURKISH_MODEL if piper_ready else system_voice,
        "turkce": piper_ready or system_voice is not None,
        "model_kurulu": piper_ready,
        "yukseltme": hint,
    }
