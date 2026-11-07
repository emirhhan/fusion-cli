"""Açık sıra iddiaları için asgari metinsel kanıt; anlamsal denetimin yerine geçmez."""

from __future__ import annotations

import re
from collections.abc import Iterable

_EN_UNITS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")
_TR_UNITS = (
    "birinci",
    "ikinci",
    "üçüncü",
    "dördüncü",
    "beşinci",
    "altıncı",
    "yedinci",
    "sekizinci",
    "dokuzuncu",
)
_WORDS = {word: value for words in (_EN_UNITS, _TR_UNITS) for value, word in enumerate(words, 1)}
_WORDS.update(
    {
        word: value
        for value, word in enumerate(
            (
                "tenth",
                "eleventh",
                "twelfth",
                "thirteenth",
                "fourteenth",
                "fifteenth",
                "sixteenth",
                "seventeenth",
                "eighteenth",
                "nineteenth",
            ),
            10,
        )
    }
)
for _tens, _en, _en_ordinal, _tr, _tr_ordinal in (
    (10, "", "tenth", "on", "onuncu"),
    (20, "twenty", "twentieth", "yirmi", "yirminci"),
    (30, "thirty", "thirtieth", "otuz", "otuzuncu"),
    (40, "forty", "fortieth", "kırk", "kırkıncı"),
    (50, "fifty", "fiftieth", "elli", "ellinci"),
    (60, "sixty", "sixtieth", "altmış", "altmışıncı"),
    (70, "seventy", "seventieth", "yetmiş", "yetmişinci"),
    (80, "eighty", "eightieth", "seksen", "sekseninci"),
    (90, "ninety", "ninetieth", "doksan", "doksanıncı"),
):
    _WORDS[_en_ordinal] = _WORDS[_tr_ordinal] = _tens
    for _units, _prefix in ((_EN_UNITS, _en), (_TR_UNITS, _tr)):
        if _prefix:
            _WORDS.update(
                {f"{_prefix} {word}": _tens + value for value, word in enumerate(_units, 1)}
            )

_WORD_PATTERN = "|".join(
    re.escape(word).replace(r"\ ", r"[-\s]+") for word in sorted(_WORDS, key=len, reverse=True)
)
_CARDINALS = {
    word: value
    for value, word in enumerate(
        ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine"), 1
    )
}
_HUNDREDS = re.compile(
    r"\b(?P<hundreds>" + "|".join(_CARDINALS) + r")[-\s]+hundred(?:[-\s]+and)?[-\s]+"
    r"(?P<tail>" + _WORD_PATTERN + r")\b"
)
_ORDINAL = re.compile(
    r"(?<![\w.])(?:(?P<digits>\d+)(?:st|nd|rd|th)|(?P<word>" + _WORD_PATTERN + r"))(?!\w)",
    re.I,
)
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\b"
)
_DATE_BEFORE = re.compile(_MONTH + r"\.?\s*(?:the\s+)?$")
_DATE_AFTER = re.compile(r"\s*(?:of\s+)?" + _MONTH)
_NONORDINAL_COMPOUND = re.compile(r"[-\s]+(?:class|party|hand|rate)\b")
_CARDINAL = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand"
)
_DURATION = re.compile(
    r"\b(?:a|an)\s+(?:(?:" + _CARDINAL + r")[-\s]+){1,6}second\b|"
    r"\b(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[-\s]+second"
    r"(?=[-\s]+(?:intervals?|timeouts?|timers?|delays?|waits?|pauses?|durations?)\b)"
)
_SECOND_UNIT = re.compile(
    r"\b(?:\d+(?:\.\d+)?|a|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"half|quarter|per|each|every|single)(?:\s+|-)$"
)


def _explicit_ordinals(text: str) -> set[int]:
    folded = text.casefold().replace("i\u0307", "i")
    folded = _DURATION.sub(lambda match: " " * len(match.group()), folded)
    compounds = tuple(_HUNDREDS.finditer(folded))
    values = {
        _CARDINALS[match["hundreds"]] * 100 + _WORDS[re.sub(r"[-\s]+", " ", match["tail"])]
        for match in compounds
    }
    for match in _ORDINAL.finditer(folded):
        if any(compound.start() <= match.start() < compound.end() for compound in compounds):
            continue
        before, after = folded[: match.start()], folded[match.end() :]
        if _DATE_BEFORE.search(before) or _DATE_AFTER.match(after):
            continue
        if _NONORDINAL_COMPOUND.match(after):
            continue
        word = re.sub(r"[-\s]+", " ", match.group())
        if word == "second" and _SECOND_UNIT.search(before):
            continue
        values.add(int(match["digits"]) if match["digits"] else _WORDS[word])
    return values


def unbacked_ordinals(target: str, cited_sources: Iterable[str]) -> tuple[int, ...]:
    """Sadece tanınan açık sıraları karşılaştır; tarih/sürüm rakamlarından sıra türetme."""
    wanted = _explicit_ordinals(target)
    if not wanted:
        return ()
    cited = set().union(*(_explicit_ordinals(text) for text in cited_sources))
    return tuple(sorted(wanted - cited))
