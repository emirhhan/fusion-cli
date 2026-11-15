"""Riskli masaüstü eylem sınıflandırıcısı (P-008): her seferinde sorulacak eylemler.

Claude Desktop / Chrome satın alma, silme, yayınlama ve finansal işlemde ayrıca onay ister;
Terminal / Finder / System Settings için "Equivalent to shell access" uyarısı gösterir. Fusion
bunu hedef ÖĞEYE bakarak yapar (Chrome'daki `click_is_risky` ile aynı sözcük listesi):

- Tıklanan öğenin (AX rol + başlık/açıklama) adı gönder/sil/öde/çıkış türündense,
- arka plan `press` hedefinin adı öyleyse (başvuru kimliği adı taşır),
- Terminal/IDE'de Enter ya da satır sonu içeren metin (komut çalıştırır),
- sohbet uygulamalarında (Slack, Mesajlar, WhatsApp, Telegram, Discord, Teams…) düz Enter ve
  satır sonlu metin (mesajı gönderir; Shift+Enter satır ekler, sorulmaz),
- her uygulamada Cmd/Ctrl+Enter (genellikle mesajı gönderir) ve Cmd+Delete (siler/çöpe atar),
- odaktaki öğe riskli bir düğmeyken Enter,
- Sistem Ayarları'nda her eylem.

Riskli çağrı `REMOTE_DESTRUCTIVE` olur: her kipte (İzinleri atla dahil) sorulur, oturum
iznine dönüşmez. Ölçüldü (31 Ekim): `desktop_click`/`desktop_key` için çözücü yoktu;
tıklanan noktadaki öğeye hiç bakılmıyordu. Ölçüldü (31 Ekim, inceleme): `down`/`up` tık
sayılmıyordu, sohbet uygulamasında Enter göndermesi sorulmuyordu; eşleştirme rol önekini de
içerdiği için açıklamasında "post" geçen metin kutusu riskli sanılıyordu. Artık yalnız öğenin
adı aranır ve metin giriş rolleri (alan, metin alanı, arama kutusu) tıklamada riskli sayılmaz.
"""

from __future__ import annotations

import base64
import binascii
import json
import re

from ..core.desktop_settings import DesktopTarget
from ..core.tools import ToolArgs
from .args import coerce_int
from .key_spec import KeyChord, parse_key_sequence
from .risk_words import is_risky_label

SYSTEM_REASON = "{app}: sistem ayarlarını değiştirebilir; her eylem ayrıca sorulur"
CLICK_REASON = "{app} içinde {element} tıklanıyor (gönder/sil/öde türü)"
TERMINAL_ENTER_REASON = "{app} içinde Enter komutu çalıştırır"
TERMINAL_NEWLINE_REASON = "{app} içine satır sonu içeren metin yazmak komutu çalıştırır"
CHAT_ENTER_REASON = "{app} içinde Enter mesajı gönderir"
CHAT_NEWLINE_REASON = "{app} içine satır sonu içeren metin yazmak mesajı gönderir"
MOD_ENTER_REASON = "{app} içinde {chord} genellikle mesajı gönderir"
DELETE_REASON = "{app} içinde {chord} seçili öğeyi siler ya da çöpe taşır"
FOCUSED_ENTER_REASON = "{app} içinde Enter odaktaki {element} düğmesine basar"
#: Öğe okunamadı (Windows UI Automation zaman aşımı/engeli): riskli düğme denetimi yapılamaz.
UNVERIFIED_ELEMENT = "(öğe doğrulanamadı)"
UNVERIFIED_CLICK_REASON = (
    "{app} içinde tıklanan öğe doğrulanamadı (UI Automation yanıt vermedi); gönder/sil/öde "
    "düğmesi olabileceği için her tıklama sorulur"
)

#: Basılı tutma ve bırakma da öğeye basar (`down` + `up` = tık).
_CLICK_ACTIONS = frozenset({"click", "double_click", "triple_click", "middle_click", "down", "up"})
#: Tıklanınca bir şey yapmayan, yalnız odak alan metin giriş rolleri (AX öneki atılmış).
_TEXT_ROLES = frozenset({"TextField", "TextArea", "SearchField", "ComboBox", "SecureTextField"})
_ENTER = frozenset({"enter", "numpadenter"})
_DELETE = frozenset({"backspace", "forwarddelete"})
_SHELL_CATEGORIES = frozenset({"terminal", "ide"})
# These existing ordinary keypad IDs only distinguish a known control from an
# unlabelled unknown reference; they never skip the generic destructive-label gate.
_CALCULATOR_MATH_IDS = frozenset(
    [
        "Zero",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Decimal",
        "Add",
        "Subtract",
        "Multiply",
        "Divide",
        "Equals",
        "Negate",
        "Percent",
    ]
)


def risky_reason(
    tool_name: str, args: ToolArgs, target: DesktopTarget, category: str
) -> str | None:
    """Çağrı her seferinde sorulmalıysa gerekçesi; `category` = kategori anahtarı ya da ''."""
    app = target.app
    if category == "system":
        return SYSTEM_REASON.format(app=app)
    if _is_click(tool_name, args) and target.element == UNVERIFIED_ELEMENT:
        return UNVERIFIED_CLICK_REASON.format(app=app)
    if _is_click(tool_name, args) and _risky_element(target.element, clicking=True):
        return CLICK_REASON.format(app=app, element=target.element)
    if tool_name == "desktop_background_action" and args.get("action") == "press":
        if target.system_calculator is True and target.bundle == "com.apple.calculator":
            identity = _bound_calculator_identity(args, target)
            if identity is None or identity[0] != "AXButton":
                return UNVERIFIED_CLICK_REASON.format(app=app)
            # Only this native system app's exact math-reset control is exempt.
            # The native executor still checks the full current tree and reference.
            if identity[2] == "AllClear":
                return None
            if identity[2] == "ClearHistory" or not (
                identity[1].strip() or identity[3].strip() or identity[2] in _CALCULATOR_MATH_IDS
            ):
                return UNVERIFIED_CLICK_REASON.format(app=app)
        label = _ref_label(args.get("ref"))
        if label and is_risky_label(label):
            return CLICK_REASON.format(app=app, element=f"'{label}'")
    if tool_name == "desktop_type":
        text = args.get("text")
        if isinstance(text, str) and ("\n" in text or "\r" in text):
            if category in _SHELL_CATEGORIES:
                return TERMINAL_NEWLINE_REASON.format(app=app)
            if category == "chat":
                return CHAT_NEWLINE_REASON.format(app=app)
    if tool_name == "desktop_key":
        return _key_reason(args, target, category)
    return None


def _is_click(tool_name: str, args: ToolArgs) -> bool:
    if tool_name == "desktop_click":
        return True
    return tool_name == "desktop_mouse" and args.get("action", "click") in _CLICK_ACTIONS


def _split_element(element: str) -> tuple[str, str]:
    """`"Button 'Gönder'"` → ("Button", "Gönder"); rol yoksa ("", ad)."""
    role, quote, rest = element.partition(" '")
    if quote and rest.endswith("'") and role.isalnum():
        return role, rest[:-1]
    return "", element


def _risky_element(element: str, *, clicking: bool = False) -> bool:
    """Öğenin ADI riskli mi? Rol öneki aranmaz; tıklamada metin giriş rolleri riskli değildir."""
    if not element:
        return False
    role, name = _split_element(element)
    if clicking and role in _TEXT_ROLES:
        return False
    return bool(name) and is_risky_label(name)


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
        if category == "chat" and not chord.shift:
            return CHAT_ENTER_REASON.format(app=app)
        if _risky_element(target.element):
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
    human_label = " ".join(
        part for index, part in enumerate(parts) if index in (1, 3) and part
    ).strip()
    if human_label:
        return human_label
    # safeActionLabels exposes identifier-only AXButton labels when no human
    # title/description exists. Apply the same fallback to their risk gate.
    if len(parts) <= 2 or parts[0] != "AXButton":
        return ""
    # Identifiers are often CamelCase or underscore-delimited rather than prose.
    # Split only this fallback; human labels retain their existing precedence.
    identifier = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", parts[2])
    identifier = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier)
    return re.sub(r"[_\W]+", " ", identifier).strip()


def _bound_calculator_identity(
    args: ToolArgs, target: DesktopTarget
) -> tuple[str, str, str, str] | None:
    """Check the reference binding, never treat caller-provided app names as proof."""
    ref = args.get("ref")
    if not isinstance(ref, str) or not ref or len(ref) > 16_384:
        return None
    try:
        token = json.loads(base64.b64decode(ref, validate=True))
    except (binascii.Error, ValueError, RecursionError):
        return None
    if not isinstance(token, dict):
        return None
    pid, window = token.get("pid"), token.get("id")
    if (
        type(pid) is not int
        or pid <= 0
        or pid != target.pid
        or pid != coerce_int(args.get("pid"))
        or type(window) is not int
        or window <= 0
        or window != coerce_int(args.get("window_id"))
    ):
        return None
    path, fingerprint, identity = token.get("path"), token.get("fingerprint"), token.get("identity")
    if (
        not isinstance(path, list)
        or not path
        or len(path) >= 500
        or any(type(index) is not int or index < 0 for index in path)
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in fingerprint)
        or not isinstance(identity, str)
    ):
        return None
    parts = identity.split("\x1f")
    return (parts[0], parts[1], parts[2], parts[3]) if len(parts) == 4 and parts[0] else None
