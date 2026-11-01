"""Seçici içinde yazarak arama (#202, Claude Code oturum seçicisi).

Claude Code `/resume` seçicisi: `/` ya da yazdırılabilir karakterlerin çoğu arama kipine
geçer ve listeyi süzer; Esc arama kipinden çıkar (ikinci Esc seçiciyi kapatır). Gezinme
tuşları (j/k) ve Space arama başlatmaz; arama kipinde onlar da sorguya yazılır.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...ui.picker import Choice

#: Arama kipi dışında arama başlatmayan tuşlar (gezinme ve önizleme).
_NAVIGATION = frozenset({"j", "k", " "})
SEARCH_KEY = "/"


class ChoiceSearch:
    """Tüm satırlar + etkin sorgu; `query is None` arama kipinin kapalı olduğunu söyler."""

    def __init__(self, choices: Sequence[Choice]) -> None:
        self._all = tuple(choices)
        self.query: str | None = None

    @property
    def active(self) -> bool:
        return self.query is not None

    def visible(self) -> list[Choice]:
        if not self.query:
            return list(self._all)
        needle = self.query.casefold()
        return [
            choice
            for choice in self._all
            if needle in f"{choice.label} {choice.description} {choice.value}".casefold()
        ]

    def starts_search(self, char: str) -> bool:
        """Bu karakter arama kipini açar mı (kip kapalıyken)?"""
        return len(char) == 1 and char.isprintable() and char not in _NAVIGATION

    def type(self, char: str) -> bool:
        """Karakteri işle; liste değiştiyse True."""
        if not self.active:
            if not self.starts_search(char):
                return False
            self.query = "" if char == SEARCH_KEY else char
            return True
        if len(char) == 1 and char.isprintable():
            self.query = f"{self.query}{char}"
            return True
        return False

    def backspace(self) -> bool:
        if not self.query:
            return False
        self.query = self.query[:-1]
        return True

    def exit(self) -> bool:
        """Arama kipinden çık; kip zaten kapalıysa False (Esc seçiciyi kapatır)."""
        if not self.active:
            return False
        self.query = None
        return True
