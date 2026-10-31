"""Riskli masaüstü eylem sınıflandırıcısı (P-008): her seferinde sorulacak eylemler.

Claude Desktop / Chrome satın alma, silme, yayınlama ve finansal işlemde ayrıca onay ister;
Terminal / Finder / System Settings için "Equivalent to shell access" uyarısı gösterir. Fusion
bunu hedef ÖĞEYE bakarak yapar (Chrome'daki `click_is_risky` ile aynı sözcük listesi):

- Tıklanan öğenin (AX rol + başlık/açıklama) adı gönder/sil/öde/çıkış türündense,
- arka plan `press` hedefinin adı öyleyse (başvuru kimliği adı taşır),
- Terminal/IDE'de Enter ya da satır sonu içeren metin (komut çalıştırır),
- her uygulamada Cmd/Ctrl+Enter (genellikle mesajı gönderir) ve Cmd+Delete (siler/çöpe atar),
- odaktaki öğe riskli bir düğmeyken Enter,
- Sistem Ayarları'nda her eylem.

Riskli çağrı `REMOTE_DESTRUCTIVE` olur: her kipte (İzinleri atla dahil) sorulur, oturum
iznine dönüşmez. Ölçüldü (31 Ekim): `desktop_click`/`desktop_key` için çözücü yoktu;
tıklanan noktadaki öğeye hiç bakılmıyordu.
"""

from __future__ import annotations

import base64
import binascii
import json

from ..core.desktop_settings import DesktopTarget
from ..core.tools import ToolArgs
from .key_spec import KeyChord, parse_key_sequence
from .risk_words import is_risky_label

SYSTEM_REASON = "{app}: sistem ayarlarını değiştirebilir; her eylem ayrıca sorulur"
CLICK_REASON = "{app} içinde {element} tıklanıyor (gönder/sil/öde türü)"
TERMINAL_ENTER_REASON = "{app} içinde Enter komutu çalıştırır"
TERMINAL_NEWLINE_REASON = "{app} içine satır sonu içeren metin yazmak komutu çalıştırır"
MOD_ENTER_REASON = "{app} içinde {chord} genellikle mesajı gönderir"
DELETE_REASON = "{app} içinde {chord} seçili öğeyi siler ya da çöpe taşır"
FOCUSED_ENTER_REASON = "{app} içinde Enter odaktaki {element} düğmesine basar"

_CLICK_ACTIONS = frozenset({"click", "double_click", "triple_click", "middle_click"})
_ENTER = frozenset({"enter", "numpadenter"})
_DELETE = frozenset({"backspace", "forwarddelete"})
_SHELL_CATEGORIES = frozenset({"terminal", "ide"})


def risky_reason(
    tool_name: str, args: ToolArgs, target: DesktopTarget, category: str
) -> str | None:
    """Çağrı her seferinde sorulmalıysa gerekçesi; `category` = kategori anahtarı ya da ''."""
    app = target.app
    if category == "system":
        return SYSTEM_REASON.format(app=app)
    if _is_click(tool_name, args) and target.element and is_risky_label(target.element):
        return CLICK_REASON.format(app=app, element=target.element)
    if tool_name == "desktop_background_action" and args.get("action") == "press":
        label = _ref_label(args.get("ref"))
        if label and is_risky_label(label):
            return CLICK_REASON.format(app=app, element=f"'{label}'")
    if tool_name == "desktop_type":
        text = args.get("text")
        if (
            category in _SHELL_CATEGORIES
            and isinstance(text, str)
            and ("\n" in text or "\r" in text)
        ):
            return TERMINAL_NEWLINE_REASON.format(app=app)
    if tool_name == "desktop_key":
        return _key_reason(args, target, category)
    return None


def _is_click(tool_name: str, args: ToolArgs) -> bool:
    if tool_name == "desktop_click":
        return True
    return tool_name == "desktop_mouse" and args.get("action", "click") in _CLICK_ACTIONS


def _key_reason(args: ToolArgs, target: DesktopTarget, category: str) -> str | None:
    raw = args.get("key")
    if not isinstance(raw, str):
        return None
    try:
        chords = parse_key_sequence(raw)
    except ValueError:
        # Ayrıştırılamayan dizgiyi araç kendisi reddeder; burada tahmin yürütülmez.
        return None
    for chord in chords:
        reason = _chord_reason(_with_legacy_flags(chord, args), target, category)
        if reason is not None:
            return reason
    return None


def _with_legacy_flags(chord: KeyChord, args: ToolArgs) -> KeyChord:
    """Eski `command`/`control` boolean bayrakları akora eklenir (araçla aynı kural)."""
    flags = {name: args.get(name) is True for name in ("command", "shift", "option", "control")}
    return chord.with_flags(**flags)


def _chord_reason(chord: KeyChord, target: DesktopTarget, category: str) -> str | None:
    app, label = target.app, chord.label()
    if chord.key in _ENTER:
        if category in _SHELL_CATEGORIES:
            return TERMINAL_ENTER_REASON.format(app=app)
        if chord.command or chord.control:
            return MOD_ENTER_REASON.format(app=app, chord=label)
        if target.element and is_risky_label(target.element):
            return FOCUSED_ENTER_REASON.format(app=app, element=target.element)
    if chord.key in _DELETE and chord.command:
        return DELETE_REASON.format(app=app, chord=label)
    return None


def _ref_label(ref: object) -> str:
    """Arka plan başvurusundaki öğe adı (kimlik: rol␟başlık␟tanımlayıcı␟açıklama)."""
    if not isinstance(ref, str) or not ref:
        return ""
    try:
        token = json.loads(base64.b64decode(ref, validate=True))
    except (binascii.Error, ValueError):
        return ""
    identity = token.get("identity") if isinstance(token, dict) else None
    if not isinstance(identity, str):
        return ""
    parts = identity.split("\u001f")
    return " ".join(part for index, part in enumerate(parts) if index in (1, 3) and part).strip()
