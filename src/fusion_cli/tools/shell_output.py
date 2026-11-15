"""Kabuk çıktısının modele nasıl ulaşacağı: Claude Code Bash çıktı sınırları (#357).

Claude Code (tools-reference, "Output limits"):
- Geçerli sonuç ~30.000 karaktere kadar satır içi; aşınca oturum dizinine kaydedilen dosyanın
  yolu (64 MiB'de kesilir) ve ilk 2.000 karakterlik önizleme.
- Hatalı sonuç ~10.000 karaktere kadar satır içi; aşınca geri okuma penceresinden o boyda
  baş+son kesit, dosya yolu yok.
- Çıkış kodu 1 yalnız `grep`, `rg`, `egrep`, `fgrep`, `find`, `diff`, `test`, `[`, `git diff`,
  `git grep` için geçerli sayılır.
- `BASH_MAX_OUTPUT_LENGTH` geri okuma penceresidir (varsayılan 30.000, tavan 150.000);
  `bashOutputMaxChars` ayarı (≤128.000) satır içi sınırı ve pencereyi birlikte belirler, o
  zaman ortam değişkeni yok sayılır.
"""

from __future__ import annotations

from pathlib import Path

from ..config.claude_settings import claude_setting
from ..core.artifacts import PREVIEW_CHARS, ArtifactStore
from .auto_policy import command_words
from .bash_settings import DEFAULT_OUTPUT_CHARS, output_limit

FAILURE_INLINE_CHARS = 10_000
WINDOW_CEILING_CHARS = 150_000
SETTING_CEILING_CHARS = 128_000
#: Dosyaya kaydedilen tam çıktının üst sınırı (64 MiB).
SAVED_OUTPUT_CHARS = 64 * 1024 * 1024
_BENIGN_EXIT_ONE = frozenset({"grep", "rg", "egrep", "fgrep", "find", "diff", "test", "["})
_BENIGN_GIT = frozenset({"diff", "grep"})
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})


def output_limits(root: Path) -> tuple[int, int]:
    """(geçerli sonucun satır içi sınırı, geri okuma penceresi)."""
    configured = claude_setting(root, "bashOutputMaxChars")
    if isinstance(configured, int) and not isinstance(configured, bool) and configured > 0:
        size = min(configured, SETTING_CEILING_CHARS)
        return size, size
    return DEFAULT_OUTPUT_CHARS, min(output_limit(), WINDOW_CEILING_CHARS)


def is_benign_exit(command: str, code: int) -> bool:
    """Bu çıkış kodu Bash aracı için geçerli sonuç mu?

    Boru ve zincirde çıkış kodu son çalışan komutundur: `cat f | grep x`, `cd src && grep x`
    son parçaya göre değerlendirilir; öndeki ortam atamaları ve git'in genel seçenekleri
    (`-C dizin`, `--no-pager`) atlanır.
    """
    if code == 0:
        return True
    if code != 1:
        return False
    segments = command_words(command)
    if not segments:
        return False
    words = segments[-1]
    head = Path(words[0]).name
    if head == "git":
        rest = words[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in _GIT_VALUE_OPTIONS else rest[1:]
        return bool(rest) and rest[0] in _BENIGN_GIT
    return head in _BENIGN_EXIT_ONE


def _head_tail(text: str, size: int) -> str:
    if len(text) <= size:
        return text
    half = size // 2
    dropped = len(text) - 2 * half
    return f"{text[:half]}\n[… {dropped} karakter atıldı (çıktı çok uzun) …]\n{text[-half:]}"


def shape_output(
    text: str, *, valid: bool, inline: int, window: int, store: ArtifactStore | None
) -> tuple[str, Path | None]:
    """Çıktıyı Claude kuralına göre biçimle; dosyaya alındıysa yolunu da döndür."""
    readable = _head_tail(text, window)
    if not valid:
        return _head_tail(readable, FAILURE_INLINE_CHARS), None
    if len(text) <= inline:
        return readable, None
    if store is None:
        return f"{text[:inline]}\n\n[… komut çıktısı {inline} karakterde KIRPILDI.]", None
    try:
        path = store.write("run_shell", text[:SAVED_OUTPUT_CHARS])
    except OSError:
        return f"{text[:inline]}\n\n[… komut çıktısı {inline} karakterde KIRPILDI.]", None
    note = (
        f"\n\n[… çıktı {len(text)} karakter; tamamı dosyada: {path}\n"
        f'Gerekirse read_file(path="{path}") ya da search_code ile oku.]'
    )
    return f"{text[:PREVIEW_CHARS]}{note}", path
