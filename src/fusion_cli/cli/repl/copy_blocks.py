"""`/copy [N]` blok seçicisi (#231, Claude Code).

Claude Code: cevapta kod bloğu ya da alıntı varsa `/copy` tek tek blokları ya da tam yanıtı
seçtiren bir seçici açar. Bu modül cevabı bloklara ayırır ve seçici satırlarını üretir;
seçim değeri `tam` ya da bloğun 1 tabanlı sırasıdır. Satır içi REPL `pick()`, tam ekran TUI
uygulama-içi modal, masaüstü `komut.secenekler` aynı satırları kullanır.
"""

from __future__ import annotations

import re

from ...ui import messages
from ...ui.picker import Choice

FULL = "tam"
#: Seçicide panoya değil dosyaya yazdıran tuş; seçim değeri `w:<seçim>` olur.
WRITE_KEY = "w"
WRITE_PREFIX = f"{WRITE_KEY}:"
#: Kod dili → dosya uzantısı (bilinmeyen dil `.txt`, tam yanıt/alıntı `.md`).
_EXTENSIONS = {
    "python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts",
    "tsx": "tsx", "jsx": "jsx", "bash": "sh", "sh": "sh", "shell": "sh", "zsh": "sh",
    "json": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml", "rust": "rs", "go": "go",
    "html": "html", "css": "css", "sql": "sql", "markdown": "md", "md": "md",
}
_FENCE = re.compile(r"^(```|~~~)(.*)$")


def answer_blocks(answer: str) -> list[tuple[str, str]]:
    """(tür, metin) çiftleri: fenced kod blokları (`kod:<dil>`) ve ardışık alıntı satırları."""
    blocks: list[tuple[str, str]] = []
    lines = answer.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = _FENCE.match(line.strip())
        if fence:
            marker, language = fence.group(1), fence.group(2).strip()
            body: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(marker):
                body.append(lines[index])
                index += 1
            blocks.append((f"kod:{language}" if language else "kod", "\n".join(body)))
        elif line.lstrip().startswith(">"):
            quote: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote.append(lines[index].lstrip()[1:].removeprefix(" "))
                index += 1
            blocks.append(("alıntı", "\n".join(quote)))
            continue
        index += 1
    return blocks


def copy_choices(answer: str) -> tuple[Choice, ...]:
    """Blok yoksa boş; varsa önce tam yanıt, sonra her blok."""
    blocks = answer_blocks(answer)
    if not blocks:
        return ()
    rows = [Choice(FULL, messages.COPY_CHOICE_FULL, f"{len(answer)} karakter")]
    for number, (kind, text) in enumerate(blocks, start=1):
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        rows.append(
            Choice(
                str(number),
                messages.COPY_CHOICE_BLOCK.format(number=number, kind=kind),
                f"{len(text.splitlines())} satır · {first[:60]}",
            )
        )
    return tuple(rows)


def split_write(selector: str) -> tuple[bool, str]:
    """`w:<seçim>` → (True, seçim); düz seçim → (False, seçim)."""
    if selector.startswith(WRITE_PREFIX):
        return True, selector[len(WRITE_PREFIX) :]
    return False, selector


def is_selector(word: str) -> bool:
    """`tam`, blok sırası ya da bunların `w:` ile dosyaya yazma biçimi."""
    inner = split_write(word)[1]
    return inner == FULL or (inner.isascii() and inner.isdecimal())


def extension_for(answer: str, selector: str) -> str:
    """Dosyaya yazmada uzantı: kod bloğunda dilden, tam yanıt ve alıntıda `md`."""
    blocks = answer_blocks(answer)
    if selector.isdigit() and 1 <= int(selector) <= len(blocks):
        kind = blocks[int(selector) - 1][0]
        if kind.startswith("kod"):
            return _EXTENSIONS.get(kind.partition(":")[2].lower(), "txt")
    return "md"


def select(answer: str, selector: str) -> str | None:
    """Seçime göre kopyalanacak metin; geçersiz seçimde None."""
    if selector == FULL:
        return answer
    blocks = answer_blocks(answer)
    if selector.isdigit() and 1 <= int(selector) <= len(blocks):
        return blocks[int(selector) - 1][1]
    return None
