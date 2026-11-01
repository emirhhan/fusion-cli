"""Dış `@import` onay penceresi (Claude Code #145, #166).

Belge (code.claude.com/docs/en/memory, "Import additional files"): bir projede çalışma
dizini dışını gösteren import ilk görüldüğünde dosyaları listeleyen bir onay penceresi
açılır; reddedilirse importlar kapalı kalır ve pencere bir daha görünmez. Karar proje
başına `claude_md_imports` deposunda saklanır; yüzeyler (terminal, TUI) yalnız soruyu
gösterip cevabı `record` ile yazar.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from .claude_md_imports import external_import_decision, set_external_import_decision

QUESTION = (
    "Bu projenin talimat dosyaları çalışma dizini dışındaki dosyaları içe aktarıyor:\n"
    "{files}\n"
    "Bu dış importlara izin verilsin mi? Reddedersen kapalı kalır ve bir daha sorulmaz. [e/H]"
)

APPROVED_NOTE = "Dış importlara izin verildi; bir sonraki turdan itibaren yüklenir."
DECLINED_NOTE = "Dış importlar kapalı kalacak (bir daha sorulmayacak)."

_YES = frozenset({"e", "evet", "y", "yes"})


def pending_external_imports(
    root: Path, home: Path | None, extra_roots: tuple[Path, ...] = ()
) -> tuple[Path, ...]:
    """Kararı henüz verilmemiş dış import hedefleri; karar varsa ya da yoksa boş."""
    if external_import_decision(root) is not None:
        return ()
    from .instruction_layers import load_instruction_layers

    load = load_instruction_layers(root, home, extra_roots=extra_roots)
    return tuple(dict.fromkeys((*load.pending_imports, *_external_rule_links(root))))


def _external_rule_links(root: Path) -> tuple[Path, ...]:
    """Kök dışını gösteren `.claude/rules` sembolik bağları (#166): aynı onaya bağlı."""
    kok = root.resolve()
    base = kok / ".claude" / "rules"
    if not base.is_dir():
        return ()
    found: list[Path] = []
    for path in sorted(base.rglob("*.md")):
        try:
            target = path.resolve()
        except OSError:
            continue
        if target.is_file() and not target.is_relative_to(kok):
            found.append(target)
    return tuple(found)


def question(paths: tuple[Path, ...]) -> str:
    """Kullanıcıya gösterilecek soru metni."""
    return QUESTION.format(files="\n".join(f"  - {path}" for path in paths))


def record(root: Path, answer: str) -> str:
    """Cevabı sakla; kullanıcıya gösterilecek notu döndür."""
    approved = answer.strip().lower() in _YES
    set_external_import_decision(root, approved)
    return APPROVED_NOTE if approved else DECLINED_NOTE


async def offer(
    root: Path,
    home: Path | None,
    *,
    show: Callable[[str], None],
    read_answer: Callable[[], Awaitable[str]],
    extra_roots: tuple[Path, ...] = (),
) -> bool:
    """Bekleyen dış import varsa sor ve kararı yaz; soru gösterildiyse True."""
    paths = pending_external_imports(root, home, extra_roots)
    if not paths:
        return False
    show(question(paths))
    try:
        answer = await read_answer()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    show(record(root, answer))
    return True
