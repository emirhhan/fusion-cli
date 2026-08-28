"""Diğer araçların bellek dosyalarını sistem promptuna hazırlar.

`project_instructions.py` hedef projenin KENDİ talimat dosyasını okuyor. Bu modül
onun eşleniğidir: kullanıcının başka araçlarda biriktirdiği KALICI belleği okur.
Aynı "sığ tarama" ilkesi geçerlidir — dosya varsa okunur, yoksa sessizce atlanır.
"""

from __future__ import annotations

from pathlib import Path

from .claude_source import slug_for

#: Tek bir bellek dosyasından okunacak en fazla karakter.
MAX_CHARS = 6_000


def _candidates(home: Path, root: Path) -> tuple[tuple[Path, str], ...]:
    return (
        (home / ".claude" / "projects" / slug_for(root) / "memory" / "MEMORY.md", "claude"),
        (home / ".hermes" / "memories" / "MEMORY.md", "hermes"),
        (home / ".hermes" / "memories" / "USER.md", "hermes"),
    )


def read_external_memory(home: Path, root: Path) -> str:
    """Bulunan bellek dosyalarını tek bir etiketli blok olarak döndür."""
    blocks: list[str] = []
    for path, source in _candidates(home, root):
        try:
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        trimmed = len(content) > MAX_CHARS
        if trimmed:
            content = content[:MAX_CHARS]
        suffix = "\n[…kırpıldı…]" if trimmed else ""
        blocks.append(
            f'<dis_bellek kaynak="{source}" dosya="{path.name}">\n{content}{suffix}\n</dis_bellek>'
        )
    return "\n".join(blocks)
