"""Açılışta kanca güveni sorusu (#108) — Claude Code'un çalışma alanı güven iletişimi.

Claude Code etkileşimli oturumda, kullanıcı ayarındakiler dahil hiçbir kancayı çalışma
alanı güveni kabul edilmeden çalıştırmaz. Fusion `fusion` (REPL/TUI) açılışında klasöre
güvenilmemişse ve bekleyen kanca varsa sorar; evet `fusion trust` ile aynı kaydı yazar
(klasör güveni proje ayarlarını da açar). Hayır derse oturum kancasız sürer; etkileşimsiz
girişte (boru, CI) sorulmaz. Masaüstünde aynı soruyu güven şeridi sorar.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from ..config.hooks import untrusted_hook_files
from ..config.trust import trust_project

HOOK_TRUST_TITLE = "Bu klasördeki dosyalara güveniyor musun? {root}"
HOOK_TRUST_FILES = (
    "Güvenene dek bu dosyaların kancaları (hook) çalışmaz; güvenirsen her araç çağrısında "
    "senin yetkinle çalışırlar: {files}"
)
HOOK_TRUST_SCOPE = (
    "Güven proje ayarlarını da açar (config.yaml, .claude/settings*.json, .fusion/tools)."
)
HOOK_TRUST_QUESTION = "Güven ve devam et? [e/H] "
HOOK_TRUST_YES = "Klasöre güvenildi; kancalar bu oturumdan itibaren çalışır."
HOOK_TRUST_NO = "Güvenilmedi: kancalar bu oturumda çalışmaz (`fusion trust` ile açılır)."
_YES = frozenset({"e", "evet", "y", "yes"})


def offer_hook_trust(
    root: Path,
    write: Callable[[str], None],
    ask: Callable[[str], str] = input,
    *,
    interactive: bool | None = None,
    home: Path | None = None,
) -> bool | None:
    """Gerekirse sor; güvenildiyse `True`, reddedildiyse `False`, sorulmadıysa `None`."""
    if not (sys.stdin.isatty() if interactive is None else interactive):
        return None
    files = untrusted_hook_files(root, home)
    if not files:
        return None
    write(HOOK_TRUST_TITLE.format(root=root))
    write(HOOK_TRUST_FILES.format(files=", ".join(files)))
    write(HOOK_TRUST_SCOPE)
    try:
        answer = ask(HOOK_TRUST_QUESTION)
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in _YES:
        write(HOOK_TRUST_NO)
        return False
    trust_project(root)
    write(HOOK_TRUST_YES)
    return True
