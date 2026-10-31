"""Yerel konuşma tanıma (STT) ile tek seferlik dikte — CLI `/voice` (P-072).

Ses buluta gitmez: masaüstü uygulamasıyla gelen cihaz üstü tanıma yardımcısı
(`fusion-listen`, macOS `SFSpeechRecognizer`; bkz. `desktop_build/listen/README.md`)
alt süreç olarak çalıştırılır ve satır başına bir JSON olay okunur:

    {"tur":"hazir"|"ses-basladi"|"kismi"|"son"|"ses-bitti"|"hata", "metin": "...", ...}

Aynı sözleşmeye uyan başka bir komut (ör. whisper.cpp/sherpa-onnx sarmalayıcısı) da
`runtime.voice_listener` ile verilebilir. Yardımcı bulunamazsa sessizce geçilmez:
`SpeechToTextError` ne yapılacağını söyler. Konuşma bir bölüm ("son" + "ses-bitti")
tamamlanınca, sessizlikte ya da üst süre dolunca dinleme biter.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import FusionError

#: Paketli uygulamadaki yardımcının adı (Rust `speech_helper_resource_name` ile aynı).
LISTENER_NAME = "fusion-listen.exe" if sys.platform == "win32" else "fusion-listen"
#: Yardımcının aranacağı yerler: kurulu uygulama, sonra kaynak ağacı (geliştirme).
_SOURCE_RESOURCE = Path(__file__).resolve().parents[3] / "app" / "src-tauri" / "resources"
_APP_RESOURCES = Path("Fusion.app") / "Contents" / "Resources"
#: Hiç ses gelmezse dinleme bu kadar sonra biter (sn).
NO_SPEECH_TIMEOUT_S = 12.0
#: Tek dikte en çok bu kadar sürer (sn).
MAX_LISTEN_S = 90.0
#: Yardımcıya SIGTERM sonrası kapanması için tanınan süre (sn).
_STOP_GRACE_S = 2.0
#: Yardımcının bildirdiği bilinen hata kodları → kullanıcı metni.
_ERROR_HINTS = {
    "dikte_kapali": (
        "macOS Siri ve Dikte kapalı. Sistem Ayarları › Klavye › Dikte'yi açıp yeniden dene."
    ),
}


class SpeechToTextError(FusionError):
    """Dikte yapılamadı; mesaj kullanıcıya olduğu gibi gösterilir."""


@dataclass(frozen=True, slots=True)
class Dictation:
    """Tanınan metin (boş olabilir: hiç konuşulmadı)."""

    text: str


def listener_dirs() -> tuple[Path, ...]:
    """Yardımcının aranacağı klasörler, öncelik sırasıyla."""
    return (
        Path("/Applications") / _APP_RESOURCES,
        Path.home() / "Applications" / _APP_RESOURCES,
        _SOURCE_RESOURCE,
    )


def find_listener(configured: str = "", dirs: Sequence[Path] | None = None) -> Path | None:
    """Ayardaki yol (ya da PATH'teki ad) → kurulu uygulama → kaynak ağacı."""
    if configured.strip():
        candidate = Path(configured.strip()).expanduser()
        if candidate.is_file():
            return candidate
        found = shutil.which(configured.strip())
        return Path(found) if found else None
    for folder in dirs if dirs is not None else listener_dirs():
        candidate = folder / LISTENER_NAME
        if candidate.is_file():
            return candidate
    return None


def missing_listener_message(configured: str) -> str:
    if configured.strip():
        return f"Konuşma tanıma komutu bulunamadı: {configured} (runtime.voice_listener)."
    return (
        "Yerel konuşma tanıma bulunamadı. Fusion masaüstü uygulamasını kur (fusion-listen "
        "yardımcısı onunla gelir) ya da aynı JSON satır sözleşmesine uyan bir komutu "
        "runtime.voice_listener ile ver. Ses buluta gönderilmez."
    )


async def listen_once(
    command: Sequence[str],
    *,
    on_partial: Callable[[str], None] = lambda _text: None,
    no_speech_timeout_s: float = NO_SPEECH_TIMEOUT_S,
    max_listen_s: float = MAX_LISTEN_S,
) -> Dictation:
    """Yardımcıyı çalıştır, bir konuşma bölümünü metne çevir, süreci kapat."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as error:
        raise SpeechToTextError(f"Konuşma tanıma başlatılamadı: {error}") from error
    try:
        async with asyncio.timeout(max_listen_s):
            return await _read_dictation(process, on_partial, no_speech_timeout_s)
    except TimeoutError:
        return Dictation("")
    finally:
        await _stop(process)


async def _read_dictation(
    process: asyncio.subprocess.Process,
    on_partial: Callable[[str], None],
    no_speech_timeout_s: float,
) -> Dictation:
    if process.stdout is None:
        raise SpeechToTextError("Konuşma tanıma çıktısı okunamadı.")
    finals: list[str] = []
    speaking = False
    while True:
        wait = None if speaking or finals else no_speech_timeout_s
        try:
            raw = await asyncio.wait_for(process.stdout.readline(), wait)
        except TimeoutError:
            return Dictation(" ".join(finals))
        if not raw:
            # Yardımcı kapandı: elde ne varsa o.
            return Dictation(" ".join(finals))
        event = _event(raw)
        kind, text = event.get("tur", ""), str(event.get("metin", "")).strip()
        if kind == "hata":
            hint = _ERROR_HINTS.get(str(event.get("kod", "")), "")
            raise SpeechToTextError(hint or f"Konuşma tanıma hatası: {text or 'bilinmiyor'}")
        if kind == "ses-basladi":
            speaking = True
        elif kind == "kismi" and text:
            on_partial(text)
        elif kind == "son" and text:
            finals.append(text)
        elif kind == "ses-bitti":
            speaking = False
            if finals:
                return Dictation(" ".join(finals))


def _event(raw: bytes) -> dict[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _stop(process: asyncio.subprocess.Process) -> None:
    """Yardımcıyı SIGTERM ile kapat (mikrofonu bırakır), uzarsa öldür."""
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), _STOP_GRACE_S)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
