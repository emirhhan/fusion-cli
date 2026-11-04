"""Web kaynağı tarih beyanı, arama özeti ve filtre doğrulaması (ağsız)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser

from ..core.protocols import Clock
from ..core.tools import ToolArgs

CONTENT_SUMMARY_CHARS = 1000
DATE_UNKNOWN = "Yayın tarihi bilinmiyor; sonuçları açarak doğrula."


def timestamp(clock: Clock) -> str:
    """Enjekte edilen duvar saatini açık UTC saat dilimiyle taşı."""
    return datetime.fromtimestamp(clock.now(), UTC).isoformat()


def search_date_filter(args: ToolArgs, searched_at: str) -> str:
    """DDG tarih aralığını üret; tarih yoksa güncellik uydurma."""
    recency = args.get("recency_days")
    start, end = args.get("date_from"), args.get("date_to")
    if recency is not None:
        if isinstance(recency, bool) or not isinstance(recency, int) or recency <= 0:
            raise ValueError("recency_days pozitif tam sayı olmalı.")
        if start is not None or end is not None:
            raise ValueError("recency_days ile tarih aralığı birlikte kullanılamaz.")
        today = datetime.fromisoformat(searched_at).date()
        try:
            return f"{today - timedelta(days=recency)}..{today}"
        except OverflowError as error:
            raise ValueError("recency_days desteklenen tarih aralığını aşıyor.") from error
    if start is None and end is None:
        return ""
    if not isinstance(start, str) or not isinstance(end, str):
        raise ValueError("date_from ve date_to birlikte YYYY-MM-DD biçiminde verilmeli.")
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as error:
        raise ValueError("Tarihler YYYY-MM-DD biçiminde geçerli tarihler olmalı.") from error
    if first > last:
        raise ValueError("date_from, date_to tarihinden sonra olamaz.")
    return f"{first.isoformat()}..{last.isoformat()}"


class PageDates(HTMLParser):
    """Yalnız açık meta beyanlarını oku; gövde metninden tarih tahmin etme."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.published_at: str | None = None
        self.updated_at: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        name = values.get("property") or values.get("itemprop") or values.get("name")
        content = values.get("content")
        if name in {"article:published_time", "datePublished"} and content:
            self.published_at = content
        if name in {"article:modified_time", "dateModified"} and content:
            self.updated_at = content


@dataclass
class SearchEntry:
    """HTML ayrıştırıcısının tek sonuç üzerinde topladığı beyanlar."""

    href: str
    title: str = ""
    snippet: str = ""
    published_at: str = ""


class SearchEntries(HTMLParser):
    """Başlık ve onu izleyen snippet/zaman etiketini aynı kaynağa bağla."""

    def __init__(self, css_class: str) -> None:
        super().__init__(convert_charrefs=True)
        self.css_class = css_class
        self.entries: list[SearchEntry] = []
        self._field = ""
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "a" and self.css_class in classes and values.get("href"):
            self.entries.append(SearchEntry(values["href"] or ""))
            self._field, self._depth = "title", 1
        elif self._field:
            if tag not in {"br", "img", "meta", "input", "hr", "link"}:
                self._depth += 1
        elif self.entries:
            if "result__snippet" in classes or "result-snippet" in classes:
                self._field, self._depth = "snippet", 1
            elif "result__timestamp" in classes or tag == "time":
                self._field, self._depth = "published_at", 1
                self.entries[-1].published_at = values.get("datetime") or ""

    def handle_endtag(self, tag: str) -> None:
        if self._field:
            self._depth -= 1
            if self._depth == 0:
                self._field = ""

    def handle_data(self, data: str) -> None:
        if self._field and self.entries:
            entry = self.entries[-1]
            if self._field == "published_at" and entry.published_at:
                return
            setattr(entry, self._field, getattr(entry, self._field) + data)
