"""Açılışta klasör güveni sorusu (#71) — Claude Code'un çalışma alanı güven iletişimi gibi.

Claude Code yeni bir klasörde açılınca "Bu klasördeki dosyalara güveniyor musun?" diye sorar;
onaylanmadan proje ayarlarının allow kuralları, ek dizinleri ve kancaları etkin olmaz.
Fusion bu soruyu etkileşimli oturumun (`fusion`) açılışında, proje ayar dosyası var ama
klasöre güvenilmiyorsa sorar ve güvenilince etkin olacak allow kurallarını listeler. Cevap
evet ise `fusion trust` ile aynı kayıt yazılır; hayır ise oturum güvensiz sürer (deny/ask yine
uygulanır). Etkileşimsiz girişte (boru, CI) sorulmaz.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from ..config.permission_rules import PermissionDecision, list_rule_rows, load_permission_rules
from ..config.trust import trust_project

TRUST_TITLE = "Bu klasördeki proje ayarlarına güveniyor musun? {root}"
TRUST_RULES = "Güvenince etkin olacak allow kuralları:"
TRUST_NO_RULES = "Proje ayarı ek dizin, kanca ya da başka yürütme ayarı içerebilir."
TRUST_QUESTION = "Güven ve devam et? [e/H] "
TRUST_YES = "Klasöre güvenildi; proje ayarları bu oturumdan itibaren etkin."
TRUST_NO = "Güvenilmedi: proje allow kuralları ve kancaları atlanır (`fusion trust` ile açılır)."
_YES = frozenset({"e", "evet", "y", "yes"})
#: Listede gösterilen en çok kural; fazlası "… ve N kural daha" olur.
_MAX_LISTED = 12


def untrusted_allow_rules(root: Path) -> tuple[str, ...] | None:
    """Güvenilmeyen proje katmanı varsa güvenle açılacak allow kuralları; yoksa `None`."""
    if not load_permission_rules(root).untrusted_layers:
        return None
    return tuple(
        row.pattern
        for row in list_rule_rows(root)
        if row.source.endswith("(güvenilmiyor)") and row.decision == PermissionDecision.ALLOW.value
    )


def offer_startup_trust(
    root: Path,
    write: Callable[[str], None],
    ask: Callable[[str], str] = input,
    *,
    interactive: bool | None = None,
) -> bool | None:
    """Gerekirse sor; güvenildiyse `True`, reddedildiyse `False`, sorulmadıysa `None`."""
    if not (sys.stdin.isatty() if interactive is None else interactive):
        return None
    rules = untrusted_allow_rules(root)
    if rules is None:
        return None
    write(TRUST_TITLE.format(root=root))
    if rules:
        write(TRUST_RULES)
        for pattern in rules[:_MAX_LISTED]:
            write(f"  {pattern}")
        if len(rules) > _MAX_LISTED:
            write(f"  … ve {len(rules) - _MAX_LISTED} kural daha")
    else:
        write(TRUST_NO_RULES)
    try:
        answer = ask(TRUST_QUESTION)
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in _YES:
        write(TRUST_NO)
        return False
    trust_project(root)
    write(TRUST_YES)
    return True
