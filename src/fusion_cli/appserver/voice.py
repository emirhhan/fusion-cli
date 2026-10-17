"""Sesli yanıt: Fusion'ın kullanıcıyla konuşması.

Tasarım kararı — BEDAVA ve ÇEVRİMDIŞI: EMA Lightning (Türkçe, ~34 MB ONNX) uygulamayla
gelir ve kullanılabiliyorsa o, değilse işletim sisteminin kendi sentezleyicisi
kullanılır. Konuşma sırasında API anahtarı istenmez ve metin ağa çıkmaz.
Kullanıcının kotası ve gizliliği etkilenmez.

Türkçe uyumu ölçüldü: macOS'ta `Yelda tr_TR` sesi kuruludur.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from .prepared_voice import PreparedVoiceStore

#: Sentezleyiciye verilecek metnin üst sınırı. Uzun cevabın tamamını okumak
#: kullanıcıyı bekletir; arayüz gerekiyorsa parça parça gönderir.
MAX_SPEECH_CHARS = 4_000
CANCEL_TIMEOUT_SECONDS = 0.5

# Yalnız Fusion'ın başlattığı TTS süreçleri yönetilir. Sistem genelinde
# `killall say` çalıştırmak başka bir uygulamanın erişilebilirlik sesini de
# kesebiliyordu. PID kaydı aynı zamanda Talk penceresinin gerçek bitiş anını
# beklemesini sağlar.
_SPEECH_LOCK = threading.RLock()
_SPEECH_LIFECYCLE_LOCK = threading.RLock()
_SPEECH_PROCESSES: dict[str, tuple[subprocess.Popen[Any], Path | None]] = {}
_SPEECH_PID_TURNS: dict[int, str] = {}
_ACTIVE_SPEECH_TURN: str | None = None
_REAPING_SPEECH: tuple[subprocess.Popen[Any], Path | None] | None = None


class SpeechPlayerBusyError(RuntimeError):
    """Onceki oynaticinin cikisi henuz OS tarafindan dogrulanmadi."""


def _register_speech_process(
    process: subprocess.Popen[Any], cleanup: Path | None = None, *, turn_id: str | None = None
) -> str:
    global _ACTIVE_SPEECH_TURN
    identifier = turn_id or uuid.uuid4().hex
    with _SPEECH_LIFECYCLE_LOCK:
        with _SPEECH_LOCK:
            previous = _ACTIVE_SPEECH_TURN
        if previous is not None and previous != identifier:
            stop(previous)
        with _SPEECH_LOCK:
            _SPEECH_PROCESSES[identifier] = (process, cleanup)
            _SPEECH_PID_TURNS[process.pid] = identifier
            _ACTIVE_SPEECH_TURN = identifier
    return identifier


def _spawn_speech_process(
    argv: list[str], cleanup: Path | None = None
) -> tuple[subprocess.Popen[Any], str]:
    """Etkin oynaticiyi kesip yenisini tek lifecycle gecisinde baslat."""
    with _SPEECH_LIFECYCLE_LOCK:
        if _REAPING_SPEECH is not None:
            raise SpeechPlayerBusyError
        stop()
        if _REAPING_SPEECH is not None:
            raise SpeechPlayerBusyError
        process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return process, _register_speech_process(process, cleanup)


def _cleanup_speech_file(cleanup: Path | None) -> None:
    if cleanup is not None:
        with contextlib.suppress(OSError):
            cleanup.unlink(missing_ok=True)


def _reap_speech_process(process: subprocess.Popen[Any], cleanup: Path | None) -> None:
    global _REAPING_SPEECH
    try:
        process.wait()
    except (OSError, subprocess.SubprocessError):
        # Cikis dogrulanmadi: fail-closed sentinel yeni spawn'i engellemeye
        # devam eder. Sahipligi erken birakmak iki OS oynaticisini bindirirdi.
        return
    _cleanup_speech_file(cleanup)
    with _SPEECH_LIFECYCLE_LOCK:
        if (process, cleanup) == _REAPING_SPEECH:
            _REAPING_SPEECH = None


def _stop_process_with_deadline(process: subprocess.Popen[Any]) -> bool:
    """Terminate/kill icin toplam en fazla tek iptal butcesi kadar bekle."""
    deadline = time.monotonic() + CANCEL_TIMEOUT_SECONDS
    if process.poll() is not None:
        return True
    process.terminate()
    remaining = max(0.0, deadline - time.monotonic())
    try:
        process.wait(timeout=remaining)
        return True
    except subprocess.TimeoutExpired:
        process.kill()
    remaining = max(0.0, deadline - time.monotonic())
    if remaining > 0:
        try:
            process.wait(timeout=remaining)
            return True
        except subprocess.TimeoutExpired:
            pass
    return False


def _speech_busy_result() -> dict[str, Any]:
    return {
        "ok": False,
        "mesgul": True,
        "metin": "Önceki ses oynatıcısı hâlâ kapanıyor; kısa süre sonra yeniden deneyin.",
    }


def wait_for_speech(turn_or_pid: object) -> bool:
    """Fusion'a ait TTS turunu bitene kadar bekle; yabancı sahibi reddet."""
    global _ACTIVE_SPEECH_TURN
    if not isinstance(turn_or_pid, (int, str)):
        return False
    with _SPEECH_LOCK:
        identifier = str(turn_or_pid)
        if identifier not in _SPEECH_PROCESSES:
            try:
                identifier = _SPEECH_PID_TURNS.get(int(turn_or_pid), "")
            except (TypeError, ValueError):
                identifier = ""
        owned = _SPEECH_PROCESSES.get(identifier)
    if owned is None:
        return False
    process, cleanup = owned
    try:
        return_code = process.wait()
    finally:
        with _SPEECH_LOCK:
            current = _SPEECH_PROCESSES.get(identifier)
            if current is owned:
                _SPEECH_PROCESSES.pop(identifier, None)
                _SPEECH_PID_TURNS.pop(process.pid, None)
                if identifier == _ACTIVE_SPEECH_TURN:
                    _ACTIVE_SPEECH_TURN = None
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)
    return return_code == 0


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


#: Ses motorunun adı (arayüzde ve `ses.durum` yanıtında görünür).
EMA_VOICE_NAME = "EMA Lightning"


def _data_home() -> Path:
    """Kullanıcı verisinin kökü. Platforma göre değişir."""
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Fusion"
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Fusion"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "fusion"


def ema_ready() -> bool:
    """EMA model dosyaları pakette eksiksiz mi? Yarım kurulum hazır sayılmaz."""
    from .ema_synthesis import is_installed

    return is_installed()


#: Konuşma hızı çarpanı için kabul edilen aralık. Alt sınırın altında sesler
#: anlaşılmaz hızlanır, üst sınırın üstünde ağır çeker; ikisi de dinlenerek
#: bulundu.
HIZ_ARALIGI: tuple[float, float] = (0.6, 1.6)


def settings_path() -> Path:
    """Kullanıcının ses tercihleri. Model dosyasıyla aynı kökte durur."""
    return _data_home() / "voice-settings.json"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_settings() -> dict[str, Any]:
    """Kayıtlı hız tercihini döndür.

    Dosya yoksa ya da BOZUKSA varsayılana düşülür: elle düzenlenmiş bozuk bir
    JSON yüzünden konuşmanın tamamen susması kabul edilemez. EMA tek sesli ve
    tek parametreli (hız) olduğundan başka ayar tutulmaz.
    """
    hiz = 1.0
    try:
        ham = json.loads(settings_path().read_text(encoding="utf-8"))
        if isinstance(ham, dict):
            hiz = _clamp(float(ham.get("hiz", 1.0)), *HIZ_ARALIGI)
    except (OSError, ValueError, TypeError):
        hiz = 1.0
    return {"hiz": hiz}


def save_settings(data: object) -> dict[str, Any]:
    """`ses.ayar`: konuşma hızını kaydet."""
    if not isinstance(data, dict):
        return {"ok": False, "metin": "Geçersiz ayar."}
    yeni: dict[str, Any] = dict(load_settings())
    if "hiz" in data:
        try:
            yeni["hiz"] = _clamp(float(data["hiz"]), *HIZ_ARALIGI)
        except (TypeError, ValueError):
            return {"ok": False, "metin": "Hız bir sayı olmalı."}
    try:
        settings_path().parent.mkdir(parents=True, exist_ok=True)
        settings_path().write_text(json.dumps(yeni, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        return {"ok": False, "metin": f"Ayar kaydedilemedi: {error}"}
    return {"ok": True, **yeni}


def download_voice_model(_progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """`ses.model_indir`: EMA modeli uygulamayla geldiği için indirme gerekmez.

    Eski arayüzlerle uyum için istek yaşar; model dosyaları eksikse (bozuk kurulum)
    bunu dürüstçe söyler.
    """
    if ema_ready():
        return {"ok": True, "zaten": True}
    return {"ok": False, "metin": "Ses modeli dosyaları eksik; uygulamayı yeniden kur."}


def engine_for(*, ema_available: bool, system_voice: str | None) -> tuple[str | None, str | None]:
    """Hangi motorun kullanılacağını ve gerekiyorsa sebebini döndür.

    EMA varsa o tercih edilir: sistem sesinden daha doğal ve Windows'ta da
    çalışır. Kullanılamıyorsa sistem sesine düşülür ama SEBEBİ söylenir —
    sessizce daha kötü sesle konuşmak kullanıcıyı yanıltır.
    """
    if ema_available:
        return "ema", None
    if system_voice:
        return "sistem", ("Ses modeli dosyaları eksik; şimdilik sistem sesi kullanılıyor.")
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
        description = line.split("#", 1)[0].strip()
        parts = description.rsplit(None, 1)
        if len(parts) != 2:
            continue
        name, language = parts
        locale = language.replace("_", "-")
        # Ses adları boşluk içerebilir; kalite eki adla birlikte korunur.
        records.append((name, locale, name))
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


def _speak_with_ema(text: str) -> dict[str, Any]:
    """Metni EMA ile seslendirip çal.

    EMA ses dosyası üretir, çalmayı işletim sistemine bırakırız. Geçici dosya
    kullanılır: WAV başlığı taşır ve akış hâlinde çalmak platforma göre değişirdi.
    """
    import tempfile

    with _SPEECH_LIFECYCLE_LOCK:
        if _REAPING_SPEECH is not None:
            return _speech_busy_result()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as gecici:
        cikti = Path(gecici.name)
    from .ema_synthesis import synthesize_ema

    try:
        synthesize_ema(text, cikti, load_settings()["hiz"])
    except Exception as error:  # Yerel model/ONNX çalışma zamanı sınırı.
        import logging

        logging.getLogger(__name__).error(
            "EMA sentezi başarısız", extra={"error_type": type(error).__name__}
        )
        cikti.unlink(missing_ok=True)
        return {"ok": False, "metin": "Ses üretilemedi. Ses modelini kontrol et."}

    return _play_wav_file(cikti)


def _play_wav_file(cikti: Path) -> dict[str, Any]:
    """Sahipli WAV dosyasını mevcut iptal/bekleme yoluyla çal."""
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
        process, turn_id = _spawn_speech_process(calar, cikti)
    except SpeechPlayerBusyError:
        cikti.unlink(missing_ok=True)
        return _speech_busy_result()
    except OSError as error:
        cikti.unlink(missing_ok=True)
        return {"ok": False, "metin": f"Ses çalınamadı: {error}"}
    return {"ok": True, "pid": process.pid, "tur_id": turn_id, "motor": "ema"}


@lru_cache(maxsize=1)
def _prepared_store() -> PreparedVoiceStore:
    return PreparedVoiceStore()


def warm_voice(_request: object = None) -> dict[str, Any]:
    """Talk açılırken modeli yükle ve kısa yanıtları sessizce hazırla; oynatıcıya dokunma."""
    import logging
    import tempfile

    from .ema_synthesis import synthesize_ema
    from .voice_intents import local_voice_replies

    if not ema_ready():
        return {"ok": True, "hazir": False}
    try:
        with tempfile.TemporaryDirectory(prefix="fusion-voice-warm-") as directory:
            output = Path(directory) / "reply.wav"
            hiz = load_settings()["hiz"]
            for reply in local_voice_replies():
                synthesize_ema(reply, output, hiz)
    except Exception as error:  # Yerel model/dosya sistemi sınırı; sır veya söz loglanmaz.
        logging.getLogger(__name__).warning(
            "Ses ön hazırlığı tamamlanamadı", extra={"error_type": type(error).__name__}
        )
        return {
            "ok": False,
            "metin": "Ses ön hazırlığı tamamlanamadı; konuşurken yeniden denenecek.",
        }
    return {"ok": True, "hazir": True}


def prepare_voice(text: object) -> dict[str, Any]:
    """Cümleyi çalmadan hazırla; sonraki oynatma yalnız kimlikle yapılır."""
    from .ema_synthesis import synthesize_ema
    from .voice_text import prepare_speech

    if not ema_ready():
        return {"ok": False, "desteklenmiyor": True}
    content = prepare_speech(str(text or ""))
    if not content:
        return {"ok": False, "metin": "Okunacak metin boş."}
    hiz = load_settings()["hiz"]
    try:
        token = _prepared_store().prepare(lambda path: synthesize_ema(content, path, hiz))
    except Exception as error:  # Yerel sentez ve dosya sistemi sınırı.
        import logging

        logging.getLogger(__name__).error(
            "Ses hazırlama başarısız", extra={"error_type": type(error).__name__}
        )
        return {"ok": False, "metin": "Ses hazırlanamadı. Ses modelini kontrol et."}
    return {"ok": True, "hazir_id": token}


def play_prepared_voice(token: object) -> dict[str, Any]:
    """Hazırlanmış sesi bir kez mevcut oynatıcıya devret."""
    path = _prepared_store().take(token) if isinstance(token, str) else None
    if path is None:
        return {"ok": False, "metin": "Hazır ses bulunamadı veya zaten kullanıldı."}
    return _play_wav_file(path)


def discard_prepared_voice(token: object = None) -> dict[str, Any]:
    """İptal edilmiş kuyruğun geç gelen dosyalarını da temizle."""
    if token is None:
        _prepared_store().close()
    elif isinstance(token, str):
        _prepared_store().discard(token)
    return {"ok": True}


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
    with _SPEECH_LIFECYCLE_LOCK:
        if _REAPING_SPEECH is not None:
            return _speech_busy_result()
    # EMA varsa o tercih edilir: sistem sesleri Türkçe'de compact kademede
    # kalıyor ve Windows'ta Türkçe ses hiç yok.
    if ema_ready():
        return _speak_with_ema(content)

    voice = best_voice(installed_voice_records())
    try:
        argv = speak_argv(platform.system(), content, voice=voice)
    except ValueError as error:
        return {"ok": False, "metin": str(error)}
    try:
        process, turn_id = _spawn_speech_process(argv)
    except SpeechPlayerBusyError:
        return _speech_busy_result()
    except OSError as error:
        return {"ok": False, "metin": f"Sesli yanıt başlatılamadı: {error}"}
    return {"ok": True, "pid": process.pid, "tur_id": turn_id, "ses": voice}


def stop(turn_id: object = None) -> dict[str, Any]:
    """`ses.durdur`: yalnız belirtilen konuşma turunu idempotent biçimde kes."""
    global _ACTIVE_SPEECH_TURN, _REAPING_SPEECH
    identifier = str(turn_id) if isinstance(turn_id, str) and turn_id else None
    with _SPEECH_LIFECYCLE_LOCK:
        with _SPEECH_LOCK:
            targets = (
                [(identifier, _SPEECH_PROCESSES[identifier])]
                if identifier is not None and identifier in _SPEECH_PROCESSES
                else list(_SPEECH_PROCESSES.items())
                if identifier is None
                else []
            )
            for owned_id, (process, _cleanup) in targets:
                _SPEECH_PROCESSES.pop(owned_id, None)
                _SPEECH_PID_TURNS.pop(process.pid, None)
                if owned_id == _ACTIVE_SPEECH_TURN:
                    _ACTIVE_SPEECH_TURN = None
        for _owned_id, (process, cleanup) in targets:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                confirmed = _stop_process_with_deadline(process)
                if confirmed:
                    _cleanup_speech_file(cleanup)
                else:
                    _REAPING_SPEECH = (process, cleanup)
                    threading.Thread(
                        target=_reap_speech_process,
                        args=(process, cleanup),
                        daemon=True,
                    ).start()
    return {"ok": True, "durduruldu": bool(targets), "tur_id": identifier}


def status() -> dict[str, Any]:
    """`ses.durum`: hangi motor, hangi ses ve gerçekten uygulanabilir bir öneri var mı?

    Öneri KOŞULLUDUR. Daha önce burada bir hata vardı: Cem zaten kuruluyken ve
    motor EMA iken bile "Cem'i indir" deniyordu. Kurulu olanı önermek
    kullanıcıyı yanıltır; öneri yalnız gerçekten işe yarayacaksa çıkar.
    """
    records = installed_voice_records()
    system_voice = best_voice(records)
    ayar = load_settings()
    ema_available = ema_ready()
    supported = ema_available or platform.system().casefold() in ("darwin", "windows")

    if ema_available:
        # EMA devredeyken sistem sesi önerisi anlamsızdır.
        hint: str | None = None
    elif system_voice:
        hint = upgrade_hint(records)
    else:
        hint = (
            "Türkçe ses bulunamadı ve Fusion'ın ses modeli dosyaları eksik; "
            "uygulamayı yeniden kurmayı dene."
        )

    return {
        "ok": True,
        "kullanilabilir": supported,
        "motor": "ema" if ema_available else "sistem",
        "ses": EMA_VOICE_NAME if ema_available else system_voice,
        "turkce": ema_available or system_voice is not None,
        "model_kurulu": ema_available,
        "yukseltme": hint,
        "ayar": {"hiz": ayar["hiz"]},
    }
