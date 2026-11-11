"""Explicit user prohibitions projected onto the existing tool-family boundary.

This is a conservative grammar for direct instructions, not a task classifier.
It never grants a capability or infers a prohibition from external tool output.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping

from ...core.text_fold import fold_tr
from ...core.tools import ToolFamily
from .expertise import has_native_desktop_request

_FAMILY_WORDS = {
    ToolFamily.SHELL: r"\b(?:terminal|shell|komut satiri|kabuk)\b",
    ToolFamily.DESKTOP: (
        r"\b(?:bilgisayar kontrolu(?:nu)?|computer control|desktop|masaustu|tiklama|clicking)\b"
    ),
    ToolFamily.WEB: r"\b(?:web aramasi|web search|internet aramasi)\b",
    ToolFamily.BROWSER: r"\b(?:tarayici|browser)\b",
}
# Keep coordinated noun lists together: "X, Y veya Z kullanma" has one scope.
_CLAUSE = re.compile(
    r"[.!?;\n]+|\b(?:ama|fakat|ancak|but|however)\b"
    # A repeated verb starts an independent English imperative, not a noun list.
    r"|\b(?:and|or)\s+(?=(?:(?:do not|don't|never)\s+)?(?:use|run|open|call)\b)"
    # The Turkish negative verb closes its coordinated object list before a comma.
    r"|(?<=kullanma),|(?<=calistirma),|(?<=cagirma),|(?<=acma),"
    r"|(?<=basma),|(?<=yazma),|(?<=yapistirma),"
)
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


def prohibited_tool(name: str, families: frozenset[ToolFamily]) -> bool:
    """Unbound team workers/peers cannot inherit a per-turn permission envelope."""
    from ...core.tools import tool_family

    return tool_family(name) in families or bool(
        families and name in {"team_run", "SendMessage", "send_message"}
    )


# Internal action-route tokens travel through the existing inherited deny set.
# They are not tool names or grants; a mixed press/set_value tool stays usable
# for press while its prohibited input route is checked on effective arguments.
_SET_VALUE = "desktop_background_action:set_value"
_KEY_TEXT = "desktop_key:text_input"
_KEY_PASTE = "desktop_key:paste"
NATIVE_METHOD_BLOCKED = (
    "Kullanıcının bu turdaki açık yöntem sınırı bu eylemi yasaklıyor. "
    "İzin verilen yöntemlerle devam et; mümkün değilse sınırlamayı açıkla."
)
_NATIVE_QUOTED = re.compile(
    r"```.*?(?:```|\Z)|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’|"
    r"(?<!\w)'[^'\n]+'(?!\w)|^[ \t]*>[^\n]*",
    re.S | re.M,
)
_NATIVE_NEGATIVE = re.compile(
    r"\b(?:kullanma|calistirma|cagirma|basma|yazma|yapistirma)\b\s*(?:lutfen)?\s*$"
    r"|^\s*(?:please\s+)?(?:do not|don't|never)\s+(?:use|run|press|type|paste)\b"
    r"|^\s*no\s+(?:keyboard|shortcuts?|typing|text input|pasting|paste|shell|code)\b"
)
_NATIVE_META = re.compile(
    r"\b(?:demedim|demiyorum|diyelim|varsayalim|hypothetical|suppose)\b"
    r"|\b(?:yasak|gerekli)\s+degil\b|\b(?:is not|isn't|not saying|don't mean|do not mean)\b"
    r"|^\s*(?:if|eger|ornek|example|mesela|alinti)\b"
)
_KEYBOARD_WORDS = re.compile(r"\b(?:klavye\w*|kisayol\w*|keyboard|shortcuts?|keys?)\b")
_TEXT_WORDS = re.compile(r"\b(?:yazi|metin\w*|typing|type|text input|write text)\b")
_PASTE_WORDS = re.compile(r"\b(?:yapistir\w*|paste|pasting)\b")
_NATIVE_CONTEXT = re.compile(
    r"\b(?:fareyle|mouse|axpress|masaustu|desktop|native|computer use|keyboard input)\b"
)
_CODE_WORDS = re.compile(r"\b(?:kod|code|shell|kabuk|terminal|komut satiri)\b")


def native_method_denials(task: str) -> frozenset[str]:
    """Only direct user prohibitions; never infer a method from task/app identity."""
    prose = fold_tr(_NATIVE_QUOTED.sub(" ", task)).translate(str.maketrans("çğıöşü", "cgiosu"))
    native_context = _NATIVE_CONTEXT.search(prose) is not None or has_native_desktop_request(task)
    denied: set[str] = set()
    for clause in _CLAUSE.split(prose):
        if _NATIVE_META.search(clause) or not _NATIVE_NEGATIVE.search(clause):
            continue
        if _KEYBOARD_WORDS.search(clause):
            # desktop_type emits native keyboard events as well as desktop_key.
            denied.update(("desktop_key", "desktop_type"))
        if _TEXT_WORDS.search(clause):
            denied.update(("desktop_type", _SET_VALUE, _KEY_TEXT, _KEY_PASTE))
        if _PASTE_WORDS.search(clause):
            denied.add(_KEY_PASTE)
        if native_context and _CODE_WORDS.search(clause):
            denied.add("run_shell")
    return frozenset(denied)


def native_method_blocked(name: str, args: Mapping[str, object], denied: Collection[str]) -> bool:
    """Check the current action route after every trusted argument rewrite."""
    if name == "desktop_background_action":
        return _SET_VALUE in denied and args.get("action") == "set_value"
    if name != "desktop_key" or not ({_KEY_PASTE, _KEY_TEXT} & set(denied)):
        return False
    from ...tools.desktop import _key_chords

    chords = _key_chords(args)
    if isinstance(chords, str):
        return False  # Native argument validation rejects malformed chords.
    return any(
        (
            _KEY_PASTE in denied
            and (
                (chord.key == "v" and (chord.command or chord.control))
                or (chord.key == "insert" and chord.shift)
            )
        )
        or (
            _KEY_TEXT in denied
            and (len(chord.key) == 1 or chord.key == "space")
            and not (chord.command or chord.control)
        )
        for chord in chords
    )
