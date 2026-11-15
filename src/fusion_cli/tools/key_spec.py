"""Tuş dizgisi sözdizimi: `cmd+shift+4 enter` → sırayla basılacak akorlar.

Masaüstü (`desktop_key`) ve Chrome (`chrome_action key`) araçları aynı ayrıştırıcıyı
kullanır; modelin Claude computer-use / Chrome alışkanlığıyla yazdığı `ctrl+a`, `Meta+Enter`,
`cmd+shift+4 enter` biçimleri tek yerde çözülür. Ölçüldü (31 Ekim): `desktop_key` yalnız
tek tuş + dört boolean alıyordu, Chrome kendi `_key_base`'ini taşıyordu.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bir çağrıda gönderilebilecek en fazla akor (boşlukla ayrılmış).
KEY_SEQUENCE_MAX = 32
#: Dizinin tekrar sayısı üst sınırı.
REPEAT_MAX = 50
#: Tuşun basılı tutulabileceği en uzun süre (ms).
HOLD_MS_MAX = 5_000

#: Değiştirici takma adları → akor alanı.
MODIFIER_ALIASES = {
    "cmd": "command", "command": "command", "meta": "command", "super": "command",
    "win": "command",
    "ctrl": "control", "control": "control",
    "alt": "option", "option": "option", "opt": "option",
    "shift": "shift",
}  # fmt: skip
#: Başka araç takımlarının tuş adları → Fusion'ın kanonik adı.
KEY_NAME_ALIASES = {
    "return": "enter", "esc": "escape", "delete": "backspace", "del": "backspace",
    "pgup": "pageup", "page_up": "pageup", "pgdn": "pagedown", "page_down": "pagedown",
    "arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down",
    "forward_delete": "forwarddelete", "spacebar": "space", "bksp": "backspace",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class KeyChord:
    """Tek bir basım: taban tuş + değiştiriciler."""

    key: str
    command: bool = False
    shift: bool = False
    option: bool = False
    control: bool = False

    def with_flags(self, **flags: bool) -> KeyChord:
        """Eski boolean alanlarla (command/shift/option/control) birleşmiş kopya."""
        return KeyChord(
            key=self.key,
            command=self.command or flags.get("command", False),
            shift=self.shift or flags.get("shift", False),
            option=self.option or flags.get("option", False),
            control=self.control or flags.get("control", False),
        )

    def label(self) -> str:
        parts = [
            name
            for name, on in (
                ("cmd", self.command),
                ("ctrl", self.control),
                ("alt", self.option),
                ("shift", self.shift),
            )
            if on
        ]
        return "+".join([*parts, self.key])


def normalize_key_name(name: str) -> str:
    """Takma adlı, büyük/küçük harf karışık tuş adını kanonik ada indir."""
    key = name.strip().lower()
    return KEY_NAME_ALIASES.get(key, key)


def parse_chord(text: str) -> KeyChord:
    """`cmd+shift+4` tek akorunu çöz; taban tuş olmayan akor `ValueError` verir."""
    raw = text.strip()
    if not raw:
        raise ValueError("Tuş adı boş.")
    if raw == "+":
        return KeyChord(key="+")
    # `shift++` gibi: son token '+' tuşudur, öncekiler değiştiricidir.
    tokens = [*raw[:-2].split("+"), "+"] if raw.endswith("++") else raw.split("+")
    *modifiers, last = tokens
    flags = {"command": False, "shift": False, "option": False, "control": False}
    for token in modifiers:
        field = MODIFIER_ALIASES.get(token.strip().lower())
        if field is None:
            raise ValueError(f"Tuş dizgisi bozuk: {raw!r} ({token!r} değiştirici değil).")
        flags[field] = True
    base = normalize_key_name(last)
    if not base or base in MODIFIER_ALIASES:
        raise ValueError(
            f"Tuş dizgisi bozuk: {raw!r}. Yalnız değiştirici verildi; "
            "cmd+c gibi bir taban tuş ekle."
        )
    return KeyChord(key=base, **flags)


def parse_key_sequence(text: str) -> tuple[KeyChord, ...]:
    """Boşlukla ayrılmış akor dizisi (`cmd+l enter`) → sırayla basılacak akorlar."""
    pieces = text.split()
    if not pieces:
        raise ValueError("Tuş dizgisi boş.")
    if len(pieces) > KEY_SEQUENCE_MAX:
        raise ValueError(f"Tuş dizgisi en fazla {KEY_SEQUENCE_MAX} akor olabilir.")
    return tuple(parse_chord(piece) for piece in pieces)


def key_base(text: str) -> str:
    """Akorun taban tuş adı (küçük harf, takma adlar çözülmüş); '+' tuşu korunur."""
    try:
        return parse_chord(text).key
    except ValueError:
        stripped = text.strip()
        return "+" if stripped == "+" else stripped.rsplit("+", 1)[-1].strip().lower()
