"""`:emoji:` kısa kodları (#216, Claude Code "Quick commands").

Girdide `:` ile başlayan bir sözcük (en az iki harf) yazılıp Tab'a basılınca eşleşen kısa
kodlar emoji olarak önerilir; seçilen öneri sözcüğün yerine emojiyi koyar. Tablo yaygın
GitHub/Slack kısa kodlarının küçük bir alt kümesidir; harici bağımlılık yoktur.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

#: En az bu kadar harf yazılınca öneri açılır (`:` dahil değil).
MIN_PREFIX = 2
#: Bir Tab'da gösterilecek en çok öneri.
MAX_SUGGESTIONS = 12
_WORD = re.compile(r":([a-z0-9_+\-]+):?$")

EMOJI: dict[str, str] = {
    "smile": "😄",
    "smiley": "😃",
    "grin": "😁",
    "joy": "😂",
    "laughing": "😆",
    "wink": "😉",
    "blush": "😊",
    "heart_eyes": "😍",
    "thinking": "🤔",
    "neutral_face": "😐",
    "confused": "😕",
    "cry": "😢",
    "sob": "😭",
    "angry": "😠",
    "scream": "😱",
    "sweat_smile": "😅",
    "sunglasses": "😎",
    "upside_down_face": "🙃",
    "thumbsup": "👍",
    "+1": "👍",
    "thumbsdown": "👎",
    "-1": "👎",
    "clap": "👏",
    "pray": "🙏",
    "wave": "👋",
    "ok_hand": "👌",
    "muscle": "💪",
    "eyes": "👀",
    "raised_hands": "🙌",
    "point_right": "👉",
    "heart": "❤️",
    "broken_heart": "💔",
    "fire": "🔥",
    "sparkles": "✨",
    "star": "⭐",
    "boom": "💥",
    "zap": "⚡",
    "rocket": "🚀",
    "tada": "🎉",
    "100": "💯",
    "bulb": "💡",
    "bug": "🐛",
    "wrench": "🔧",
    "hammer": "🔨",
    "gear": "⚙️",
    "lock": "🔒",
    "key": "🔑",
    "memo": "📝",
    "book": "📖",
    "package": "📦",
    "chart_with_upwards_trend": "📈",
    "calendar": "📅",
    "hourglass": "⌛",
    "warning": "⚠️",
    "x": "❌",
    "white_check_mark": "✅",
    "heavy_check_mark": "✔️",
    "question": "❓",
    "exclamation": "❗",
    "no_entry": "⛔",
    "construction": "🚧",
    "recycle": "♻️",
    "art": "🎨",
    "coffee": "☕",
    "pizza": "🍕",
    "beer": "🍺",
    "cat": "🐱",
    "dog": "🐶",
    "robot": "🤖",
    "ghost": "👻",
    "skull": "💀",
    "poop": "💩",
    "sun": "☀️",
    "cloud": "☁️",
    "rainbow": "🌈",
    "snowflake": "❄️",
    "earth_africa": "🌍",
    "globe_with_meridians": "🌐",
    "computer": "💻",
    "iphone": "📱",
    "email": "📧",
    "link": "🔗",
    "mag": "🔍",
    "pushpin": "📌",
    "bell": "🔔",
    "trophy": "🏆",
    "gift": "🎁",
    "moneybag": "💰",
    "checkered_flag": "🏁",
    "turtle": "🐢",
    "snail": "🐌",
    "zzz": "💤",
}


def shortcode_prefix(word: str) -> str | None:
    """Sözcük `:kısa` biçimindeyse kodun yazılmış kısmı; değilse None."""
    match = _WORD.fullmatch(word)
    if match is None or len(match.group(1)) < MIN_PREFIX:
        return None
    return match.group(1)


def suggestions(prefix: str) -> Iterator[tuple[str, str]]:
    """(kısa kod, emoji) çiftleri: önce baştan eşleşenler, sonra içinde geçenler."""
    starts = [name for name in EMOJI if name.startswith(prefix)]
    contains = [name for name in EMOJI if prefix in name and name not in starts]
    for name in [*starts, *contains][:MAX_SUGGESTIONS]:
        yield name, EMOJI[name]
