"""Yalnız kesin kısa konuşmaları karşılayan ortak, yerel niyet kataloğu."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from importlib.resources import files


def _normalize(text: str) -> str:
    lowered = text.lower().replace("ı", "i")
    plain = "".join(
        c for c in unicodedata.normalize("NFD", lowered) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


@lru_cache(maxsize=1)
def _replies() -> tuple[frozenset[str], dict[str, str]]:
    catalog = json.loads(files(__package__).joinpath("data/voice-intents.json").read_text())
    return frozenset(_normalize(alias) for alias in catalog["aliases"]), {
        _normalize(phrase): intent["reply"]
        for intent in catalog["intents"]
        for phrase in intent["phrases"]
    }


def local_voice_reply(text: str) -> str | None:
    """Ad yalnız başta/sonda çıkarılır; kalan tüm ifade tam eşleşmelidir."""
    aliases, replies = _replies()
    words = _normalize(text).split()
    if words and words[0] in aliases:
        words.pop(0)
    if words and words[-1] in aliases:
        words.pop()
    return replies.get(" ".join(words))


def local_voice_replies() -> tuple[str, ...]:
    """Ön hazırlık ortak katalogdaki yanıtları tekilleştirerek kullanır."""
    return tuple(dict.fromkeys(_replies()[1].values()))
