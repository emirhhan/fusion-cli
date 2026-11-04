"""Explicit user prohibitions projected onto the existing tool-family boundary.

This is a conservative grammar for direct instructions, not a task classifier.
It never grants a capability or infers a prohibition from external tool output.
"""

from __future__ import annotations

import re

from ...core.text_fold import fold_tr
from ...core.tools import ToolFamily

_FAMILY_WORDS = {
    ToolFamily.SHELL: r"\b(?:terminal|shell|komut satiri|kabuk)\b",
    ToolFamily.DESKTOP: (
        r"\b(?:bilgisayar kontrolu|computer control|desktop|masaustu|tiklama|clicking)\b"
    ),
    ToolFamily.WEB: r"\b(?:web aramasi|web search|internet aramasi)\b",
    ToolFamily.BROWSER: r"\b(?:tarayici|browser)\b",
}
# Keep coordinated noun lists together: "X, Y veya Z kullanma" has one scope.
_CLAUSE = re.compile(r"[.!?;\n]+|\b(?:ama|fakat|ancak|but|however)\b")
_FORBIDDEN = re.compile(
    r"\b(?:kullanma|calistirma|cagirma|acma)\b\s*(?:lutfen)?\s*$"
    r"|^\s*(?:please\s+)?(?:do not|don\x27t|never)\s+(?:use|run|open|call)\b"
)


def forbidden_families(task: str) -> frozenset[ToolFamily]:
    """Resolve only direct prohibition clauses; quoted examples are not instructions."""
    prose = re.sub(r'```.*?```|`[^`]*`|["“][^"”\n]*["”]', "", task, flags=re.S)
    clauses = _CLAUSE.split(fold_tr(prose).translate(str.maketrans("çğıöşü", "cgiosu")))
    return frozenset(
        family
        for clause in clauses
        if _FORBIDDEN.search(clause)
        for family, words in _FAMILY_WORDS.items()
        if re.search(words, clause)
    )
