"""TUI girdisi Claude Code gibi: çok satır, dizin başına geçmiş, Ctrl+R, Ctrl+C/Ctrl+D (#195-197).

Claude Code (interactive-mode):
- Çok satır: `\\` + Enter, Option+Enter (Esc Enter), Shift+Enter, Ctrl+J; yapıştırma.
- Geçmiş: Up/Down (ve Ctrl+P/Ctrl+N) çalışma dizini başına geçmişte gezer, ardışık
  tekrarlar birleşir; Ctrl+R satır içi tersine arama.
- Ctrl+C: çalışan işi keser; boştayken ilk basış girdiyi temizler, ikincisi çıkar.
- Ctrl+D: girdi boşken 800 ms içinde iki basış çıkar; girdi doluysa sonraki karakteri siler.
- Ctrl+U satır başına kadar siler (prompt_toolkit Emacs bağı; kaydırmaya bağlı değil).

Ölçüldü (1 Kasım): TUI girdisi tek satırdı, geçmiş yoktu (Up/Down konuşmayı kaydırıyordu),
Ctrl+C tek basışta tur sürerken bile çıkıyordu; Ctrl+D/U/R kaydırmaya bağlıydı.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.keys import Keys

#: Ctrl+C / Ctrl+D çift basış penceresi (Claude Code: 800 ms).
DOUBLE_PRESS_SECONDS = 0.8
#: Girdi kutusunun en çok kaç satıra uzayacağı; fazlası kutu içinde kayar.
MAX_INPUT_ROWS = 10
#: Shift+Enter'ı ayrı dizi olarak gönderen terminaller (kitty/CSI-u, xterm modifyOtherKeys).
SHIFT_ENTER_SEQUENCES = ("\x1b[13;2u", "\x1b[27;2;13~")
#: Option+Enter (Meta+Enter) terminalde ESC CR olarak gelir; Esc'in tek tuş bağı eager
#: olduğundan ayrı bir dizi olarak tanımlanmazsa Esc+Enter'a hiç ulaşılmazdı.
META_ENTER_SEQUENCES = ("\x1b\r",)


def register_shift_enter() -> None:
    """Shift+Enter ve Option+Enter dizilerini Ctrl+J'ye (yeni satır) eşle."""
    for sequence in (*SHIFT_ENTER_SEQUENCES, *META_ENTER_SEQUENCES):
        ANSI_SEQUENCES.setdefault(sequence, Keys.ControlJ)


class DirectoryHistory(FileHistory):
    """Çalışma dizini başına girdi geçmişi (0600).

    Ardışık tekrarları `Buffer.append_to_history` zaten atlar (son kayıt aynıysa yazmaz);
    yüklenen eski oturum geçmişi de bu karşılaştırmaya girer.
    """

    def __init__(self, filename: Path) -> None:
        filename.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(str(filename))
        self._path = filename

    def store_string(self, string: str) -> None:
        super().store_string(string)
        try:
            self._path.chmod(0o600)
        except OSError:
            return


def history_path(memory_dir: Path, root: Path) -> Path:
    """`memory_dir/girdi-gecmisi/<dizin özeti>` — her proje dizininin kendi geçmişi."""
    digest = hashlib.sha256(str(root.expanduser().resolve()).encode("utf-8")).hexdigest()[:16]
    return memory_dir / "girdi-gecmisi" / digest


def submit_or_newline(buffer: Buffer) -> None:
    """Enter: satır `\\` ile bitiyorsa yeni satır, değilse gönder (tamamlama açıksa uygula)."""
    state = buffer.complete_state
    if state is not None and state.current_completion is not None:
        buffer.apply_completion(state.current_completion)
        return
    document = buffer.document
    if document.is_cursor_at_the_end and document.text.endswith("\\"):
        buffer.delete_before_cursor(1)
        buffer.insert_text("\n", fire_event=False)
        return
    buffer.validate_and_handle()


class DoublePress:
    """Aynı tuşa pencere içinde ikinci basışı ayırt eder."""

    def __init__(
        self,
        window_s: float = DOUBLE_PRESS_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_s = window_s
        self._clock = clock
        self._last = 0.0

    def press(self) -> bool:
        """İkinci basışsa True (ve sayaç sıfırlanır); ilkse zamanı kaydeder."""
        now = self._clock()
        is_double = self._last > 0.0 and now - self._last <= self._window_s
        self._last = 0.0 if is_double else now
        return is_double

    def reset(self) -> None:
        self._last = 0.0
