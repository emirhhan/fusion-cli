"""Recognize changing public facts without turning ordinary explanations into research."""

from __future__ import annotations

import re

# The caller supplies affirmative request clauses; quoted data is removed here. A date alone,
# "latest message", and local files are not requests for changing public facts.
_TEMPORAL = re.compile(
    r"\b(?:güncel|guncel|bugün\w*|bugun\w*|şu an\w*|su an\w*|"
    r"en son|latest|current|today|right now|itibarıyla|itibariyla)\b"
)
_CHANGING_TOPIC = re.compile(
    r"\b(?:sürüm\w*|surum\w*|versiyon\w*|version\w*|release\w*|"
    r"fiyat\w*|price\w*|dolar\w*|euro\w*|döviz\w*|doviz\w*|kur[uiı]?|"
    r"exchange rate\w*|stock price|gold|altın\w*|altin\w*|"
    r"hava durumu\w*|weather|haber\w*|news|başkan\w*|baskan\w*|"
    r"ceo|president|prime minister|başbakan\w*|basbakan\w*|"
    r"sefer\w*|schedule\w*|uçuş\w*|ucus\w*|maç\w*|mac sonucu\w*|score\w*)\b"
)
_LATEST_RELEASE = re.compile(r"\bson\s+(?:kararlı\s+|kararli\s+)?(?:sürüm\w*|surum\w*)\b")
_OFFICE_HOLDER = re.compile(
    r"(?:\b(?:kim|who)\b.{0,90}\b(?:ceo|president|prime minister)\b|"
    r"\b(?:ceo\w*|cumhurbaşkanı\w*|cumhurbaskani\w*|başbakan\w*|basbakan\w*)\b"
    r".{0,90}\bkim(?:dir)?\b)"
)
_QUOTED_DATA = re.compile(r'```.*?```|`[^`]*`|"[^"\n]*"|“[^”\n]*”', re.S)
_LOCAL_SOURCE = re.compile(
    r"\b(?:dosya\w*|klasör\w*|klasor\w*|readme|changelog|git diff|git log)\b"
)
_CONVERSATION_SOURCE = re.compile(
    r"\b(?:konuştuğumuz|konustugumuz|yazdığın|yazdigin|söylediğin|soyledigin|"
    r"son mesaj\w*|önceki mesaj\w*|onceki mesaj\w*)\b"
)
_CONCEPT = re.compile(r"\b(?:kavram\w*|ne demek|nasıl hesaplanır|nasil hesaplanir|concept\w*)\b")
_HISTORICAL = re.compile(
    r"\b(?:tarihinde|yılında|yilinda|o dönemde|o donemde|historical|in (?:19|20)\d{2})\b"
)


def current_fact_text(text: str) -> str:
    """Remove quoted data before clause splitting can detach its quote delimiters."""
    return _QUOTED_DATA.sub(" ", text)


def needs_current_lookup(text: str) -> bool:
    """A present fact needs a source; neither recency nor correctness is inferred here."""
    text = current_fact_text(text)
    if _LOCAL_SOURCE.search(text) or _CONVERSATION_SOURCE.search(text) or _CONCEPT.search(text):
        return False
    if _TEMPORAL.search(text) and _CHANGING_TOPIC.search(text):
        return True
    if _LATEST_RELEASE.search(text):
        return True
    return bool(_OFFICE_HOLDER.search(text) and not _HISTORICAL.search(text))
