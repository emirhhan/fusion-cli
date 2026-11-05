"""Match successful source reads to explicit requested URLs, not to arbitrary web activity."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal
from urllib.parse import urlsplit

from ...core.text_fold import fold_tr
from ...core.tools import ToolFamily, tool_family
from ..effects.detect import requested_web_urls

_SOURCE_READERS = frozenset(
    {"web_fetch", "browser_open", "browser_tab_open", "site_crawl", "site_design", "clone_site"}
)


_CONTROL_SCOPE_VOCABULARY = (
    "use using chrome to browser extension navigate visit browse new tab bagli eklenti eklentisini "
    "kullan kullanarak yeni bir sekme sekmede sekmeye sayfasini ac "
    "only just inspect list read show identify enumerate the interactive control controls "
    "button buttons link links form field fields name names label labels value values role "
    "roles state states on at in from of this that current open authorized page website url "
    "and or sadece yalniz yalnizca etkilesimli kontrol kontroller kontrolleri dugme dugmeler "
    "dugmeleri baglanti baglantilar baglantilari alan alanlar alanlari alanlarini ad adlari "
    "etiket etiketleri rol rolleri deger degerleri durum durumlari listele incele oku goster "
    "belirle bu acik mevcut yetkili sayfa sayfasi sayfasinda sayfasindaki sayfadan sayfanin "
    "adres adresinde adresindeki uzerinde uzerindeki ve veya"
)
_CONTROL_SCOPE_WORDS = frozenset(_CONTROL_SCOPE_VOCABULARY.split())


_PROHIBITION_VOCABULARY = (
    "do not dont never read inspect full page body text click anything fill submit the form "
    "or and any other site navigate type change modify nothing hicbir seye yere tiklama form "
    "formu doldurma veya gonderme ve metni metnini metin tam sayfa sayfanin sayfada "
    "degisiklik yapma yazma degistirme acma baska siteye gitme okuma inceleme"
)
_PROHIBITION_WORDS = frozenset(_PROHIBITION_VOCABULARY.split())


def _prohibition_only_clause(clause: str) -> bool:
    words = re.findall(r"[a-z_]+", clause.replace("don't", "dont"))
    negative = bool(
        re.search(
            r"^\s*(?:do not|don't|never)\b|\b(?:tiklama|doldurma|gonderme|yazma|degistirme|"
            r"acma|gitme|okuma|inceleme|yapma)\b",
            clause,
        )
    )
    return negative and set(words) <= _PROHIBITION_WORDS


def source_read_requirement(task: str) -> Literal["document", "controls", "restricted"]:
    """Keep a hard control-read boundary independently from sufficiency of the remaining request."""
    text = re.sub(
        r"https?://\S+",
        lambda match: match.group(0)[len(match.group(0).rstrip(".,;")) :],
        fold_tr(task),
    ).translate(str.maketrans("çğıöşü", "cgiosu"))
    # Detect the positive restriction BEFORE interpreting prohibitions. An uncertain
    # extra clause may make the request incomplete, but never grant a wider read.
    attached = re.search(
        r"\b(?:only|just)\s+(?:(?:inspect|list|read|show|identify|enumerate)\s+)?"
        r"(?:the\s+)?(?:interactive\s+)?(?:controls?|buttons?|links?|form\s+fields?)\b"
        r"|\b(?:sadece|yalnizca|yalniz)\s+(?:etkilesimli\s+)?"
        r"(?:kontrolleri?|dugmeleri?|baglantilari?|form\s+alanlarini?)\b",
        text,
    )
    body_restricted = re.search(
        r"\b(?:do not|don't|never)\s+(?:read|inspect|fetch|access)\s+(?:the\s+)?"
        r"(?:full\s+)?(?:body|text|document|page\s+(?:body|text))\b"
        r"|\b(?:sayfa\s+)?(?:govdesini|metnini|metni|tam metni)\s+(?:okuma|inceleme)\b",
        text,
    )
    if attached is None:
        return "restricted" if body_restricted is not None else "document"
    clauses = re.sub(r"\b(?:but|however|ama|fakat)\b", ";", text)
    clauses = re.sub(r"(?:,|\band\b|\bve\b)\s*(?=only\b|just\b|sadece\b|yalniz)", ";", clauses)
    positive = ". ".join(
        clause for clause in re.split(r"[.;\n]", clauses) if not _prohibition_only_clause(clause)
    )
    # Remove only recognized prohibition clauses. A comma followed by an extra
    # positive question is unknown and remains restricted instead of disappearing.
    if set(re.findall(r"[a-z_]+", positive)) <= _CONTROL_SCOPE_WORDS:
        return "controls"
    return "restricted"


def chrome_page_read_urls(task: str) -> tuple[str, ...]:
    """Bind one explicit browser navigation target to a following affirmative page read."""
    text = fold_tr(task).translate(str.maketrans("çğıöşü", "cgiosu"))
    if not re.search(r"\b(?:chrome|browser|tarayici|eklenti)\b", text):
        return ()
    if re.search(r"\b(?:translate|cevir|tercume|example|ornek|literal|alinti)\b", text):
        return ()
    urls = requested_web_urls(task)
    if len(urls) != 1:
        return ()
    protected = text.replace(
        fold_tr(urls[0]).translate(str.maketrans("çğıöşü", "cgiosu")), " source_target "
    )
    navigation_seen = False
    for clause in re.split(r"[.;!?\n]", protected):
        if re.search(r"\b(?:do not|don't|never)\b|\b(?:okuma|inceleme|acma|gitme)\b", clause):
            continue
        if "source_target" in clause and re.search(
            r"\b(?:open|navigate|visit|browse|ac|git)\b", clause
        ):
            navigation_seen = True
        if re.search(
            r"\b(?:files?|workspace|repository|repo|templates?|dosya\w*|sablon\w*)\b", clause
        ):
            continue
        if (
            navigation_seen
            and re.search(r"\b(?:read|inspect|list|show|oku|incele|listele|goster)\b", clause)
            and re.search(r"\b(?:page\w*|sayfa\w*)\b", clause)
        ):
            return urls
    return ()


def _source_key(url: str) -> tuple[str, str, int | None, str, str] | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        port = parsed.port
        if port == (443 if parsed.scheme.lower() == "https" else 80):
            port = None
        return parsed.scheme.lower(), host, port, parsed.path or "/", parsed.query
    except ValueError:
        return None


def requested_sources_read(
    urls: Sequence[str],
    evidence: Sequence[tuple[str, dict[str, object], bool]],
    *,
    observed_sources: Sequence[str] = (),
) -> bool:
    """Prove reads of named pages; this does not claim semantic correctness or freshness.

    Evidence is admitted only after a successful real tool execution. Matching the
    requested URL (rather than a guessed final redirect) preserves legitimate redirects.
    Search queries, downloads and browser control/status calls do not prove a page read.
    """
    seen = {
        _source_key(url)
        for name, args, _ in evidence
        if name in _SOURCE_READERS and isinstance((url := args.get("url")), str)
    }
    seen.update(_source_key(url) for url in observed_sources)
    seen.discard(None)
    return all((key := _source_key(url)) is not None and key in seen for url in urls)


def web_lookup_observed(evidence: Sequence[tuple[str, dict[str, object], bool]]) -> bool:
    """Generic research needs lookup/page access; browser status/control is not one."""
    return any(
        (tool_family(name) is ToolFamily.WEB and name != "download_file")
        or (
            name in _SOURCE_READERS
            and isinstance((url := args.get("url")), str)
            and _source_key(url) is not None
        )
        for name, args, _ in evidence
    )
