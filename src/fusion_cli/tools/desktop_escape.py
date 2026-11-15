"""Küresel Esc dinleyicisi: Fusion fareyi/klavyeyi kullanırken fiziksel Esc turu durdurur (P-033).

Claude CLI computer use: "press Esc to stop" — Esc küresel iptaldir ve tuş uygulamaya GİTMEZ
(ekrandaki bir istemin model yerine kapatılması, yani prompt injection'ın diyaloğu kapatması
engellenir). Fusion'da dinleyici yerel yardımcının `escwatch` işlemidir: oturum düzeyinde etkin
bir olay musluğu (CGEventTap, Erişilebilirlik izniyle) Esc'i yutar ve stdout'a `{"esc": true}`
yazar. Fusion'ın kendi gönderdiği Esc (`desktop_key key=esc`) olayın kaynak pid'iyle ayrılır.

Süreç tur boyunca yaşar; `stop` stdin'i kapatır (yardımcı kendiliğinden çıkar) ve süreci bekler.
Ölçüldü (31 Ekim): küresel bir durdurma yolu yoktu; kullanıcı ekranda kendi faresi ajanla
yarışırken yalnız Fusion penceresine dönüp "durdur"a basabiliyordu.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

_logger = logging.getLogger(__name__)

#: Dinleyicinin hazır olduğunu bildirmesi için beklenen süre (s); gelmezse Esc yolu yok sayılır.
ESC_READY_TIMEOUT_S = 5.0
#: Durdururken yardımcının çıkması için beklenen süre (s); sonra öldürülür.
ESC_STOP_TIMEOUT_S = 2.0

ESCAPE_EVENT = "esc"


class EscapeWatch:
    """Bir turluk Esc dinleyicisi; `on_escape` okuma iş parçacığından çağrılır."""

    def __init__(
        self,
        on_escape: Callable[[], None],
        *,
        executable: Callable[[], Path],
        ignored_pid: int | None = None,
    ) -> None:
        self._on_escape = on_escape
        self._executable = executable
        self._ignored_pid = os.getpid() if ignored_pid is None else ignored_pid
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._ready = threading.Event()
        self.error = ""

    def start(self) -> bool:
        """Dinleyiciyi başlat; hazır olursa True. Başarısızlık `error`'a yazılır, tur sürer."""
        try:
            binary = self._executable()
            self._process = subprocess.Popen(
                [str(binary), "escwatch", str(self._ignored_pid)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.error = f"Esc dinleyicisi başlatılamadı: {exc}"
            _logger.warning("Esc dinleyicisi başlatılamadı", exc_info=True)
            return False
        self._reader = threading.Thread(target=self._read, name="fusion-esc", daemon=True)
        self._reader.start()
        if not self._ready.wait(ESC_READY_TIMEOUT_S) or self.error:
            self.error = self.error or "Esc dinleyicisi hazır olmadı (Erişilebilirlik izni?)."
            self.stop()
            return False
        return True

    def _read(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw in process.stdout:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get(ESCAPE_EVENT) is True:
                self._dispatch()
            elif message.get("ok") is True:
                self._ready.set()
            else:
                self.error = str(message.get("metin") or "Esc dinleyicisi kurulamadı.")
                self._ready.set()
                return

    def _dispatch(self) -> None:
        try:
            self._on_escape()
        except Exception:  # sınır: okuma iş parçacığı ölmesin; hata günlüğe düşer
            _logger.exception("Esc işleyicisi hata verdi")

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None and not self.error

    def stop(self) -> None:
        """Yardımcıyı kapat (stdin kapanınca kendisi çıkar), gerekirse öldür; bekle."""
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=ESC_STOP_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
        if self._reader is not None and self._reader is not threading.current_thread():
            self._reader.join(timeout=ESC_STOP_TIMEOUT_S)
