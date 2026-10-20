"""HTML'nin yerel script ve stylesheet hedeflerinin dosya varlığını denetle."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from posixpath import relpath
from urllib.parse import unquote, urljoin, urlsplit


class _DependencyParser(HTMLParser):
    """Kaynak referanslarını ve belgenin ilk base etiketini topla."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.base: str | None = None
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "base" and self.base is None and attributes.get("href") is not None:
            self.base = attributes["href"]
        if tag == "script":
            source = attributes.get("src")
        elif tag == "link" and "stylesheet" in (attributes.get("rel") or "").lower().split():
            source = attributes.get("href")
        else:
            return
        if source is not None:
            self.sources.append(source)


def missing_local_dependencies(html: str, *, document: Path, root: Path) -> tuple[str, ...]:
    """Belge URL'sine göre çözülen yerel CSS/JS dosyaları yoksa bulgu üret.

    Disk okunmaz: yalnız varlık kontrol edilir. Ağ/data/blob kaynakları bu mekanik
    kapının kapsamı dışındadır; tarayıcı doğrulaması yükleme sonucunu ölçer.
    file URL'leri ve kodlanmış ayırıcılar doğrulanamadığı için engellenir.
    """
    parser = _DependencyParser()
    parser.feed(html)
    document_name = relpath(document, root)
    document_url = "/" + document_name
    # Dış çalışma kökünde üretilen belge için kendi dizini yerel sunucu köküdür.
    if document_name.startswith("../"):
        root = document.parent
        document_name = document.name
        document_url = "/" + document_name
    try:
        base_url = _join_url(document_url, parser.base) if parser.base is not None else document_url
    except ValueError:
        return (f"'{document_name}' içinde geçersiz base URL'si: {parser.base}",)
    findings: list[str] = []
    seen: set[Path] = set()
    for source in parser.sources:
        resolved = _resolve_source(source, base_url, root)
        if resolved.problem:
            findings.append(f"'{document_name}' kaynağı: {source}; {resolved.problem}")
        target = resolved.target
        if target is None or target in seen:
            continue
        seen.add(target)
        if not target.is_file():
            findings.append(f"'{document_name}' yerel kaynağı gösteriyor ama dosya yok: {source}")
    return tuple(findings)


@dataclass(frozen=True)
class _DependencyTarget:
    """Çözülen yerel hedef veya çözümün doğrulanamama sebebi."""

    target: Path | None = None
    problem: str = ""


def _resolve_source(source: str, base_url: str, root: Path) -> _DependencyTarget:
    """URL kökü semantiğiyle çöz; belirsiz taşıma davranışını başarı sayma."""
    try:
        resolved = urlsplit(_join_url(base_url, source.strip()))
    except ValueError:
        return _DependencyTarget(problem="geçersiz kaynak URL'si")
    if resolved.scheme == "file":
        return _DependencyTarget(
            problem="file URL'si bu yerel sunucu kapısında doğrulanamadı; göreli yol kullan"
        )
    if resolved.scheme or resolved.netloc or not resolved.path:
        return _DependencyTarget()
    segments: list[str] = []
    for encoded_segment in resolved.path.split("/"):
        segment = unquote(encoded_segment)
        # %2f/%5c'nin sunucular arasında farklı karşılığı vardır: ayırıcıyı
        # sessizce disk yoluna dönüştürerek var olmayan URL'yi geçmiş sayma.
        if "/" in segment or "\\" in segment:
            return _DependencyTarget(problem="kodlanmış URL ayırıcı bu kapıda doğrulanamadı")
        if segment in ("", "."):
            continue
        if segment == "..":
            if segments:
                segments.pop()
        else:
            segments.append(segment)
    return _DependencyTarget(target=root.joinpath(*segments))


def _join_url(base: str, reference: str) -> str:
    """URL çözmeden önce yalnız dot-only path segmentlerini canonical hale getir.

    urljoin literal '..' segmentlerini çözer; kodlanmış '..' önce dönüştürülmezse
    karışık zincirin sırası değişir. Query, fragment ve diğer yüzde kodları korunur.
    """

    def canonical(url: str) -> str:
        parts = urlsplit(url)
        segments = (
            decoded if (decoded := unquote(segment)) in (".", "..") else segment
            for segment in parts.path.split("/")
        )
        return parts._replace(path="/".join(segments)).geturl()

    return urljoin(canonical(base), canonical(reference))
