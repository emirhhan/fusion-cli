"""Konuşmayı düz metne, Markdown'a ya da JSON'a aktar (P-028, #206: `/export`, `/copy`).

`/export` Claude Code'daki gibi DÜZ METİN yazar (`export_text`): kullanıcı satırı `> `,
asistan ve araç çağrısı `⏺ `, araç çıktısı `  ⎿  ` girintili ve okunur. Markdown ve JSON
masaüstü paylaşımı ile `md`/`json` bayrakları içindir.

Tek üretici, üç yüzey: REPL `/export`, masaüstü ShareDialog (`sohbet.disa_aktar` RPC)
ve `/copy`. Claude Code'un `/export` davranışı örnek alınmıştır: kullanıcı ve asistan
mesajları başlıklı bölümler, araç çağrıları KATLANMIŞ (`<details>`) ve KIRPILMIŞ,
sistem istemi ve harness notları dışarıda. Sırlar `core.redaction.redact` ile
maskelenir; ham geçmiş hiçbir zaman olduğu gibi dışarı çıkmaz.

Yalnız stdlib: `core` katmanı.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence
from html import escape as html_escape

from .redaction import redact
from .types import Message, ToolCall

#: Katlanmış araç sonucunun dışa aktarımda tutulan en fazla karakteri.
TOOL_OUTPUT_CHARS = 4_000
#: Araç argümanlarının (ham JSON) kırpma sınırı.
TOOL_ARGS_CHARS = 1_000
#: Kullanıcıya görünen rol başlıkları.
ROLE_USER = "Siz"
ROLE_ASSISTANT = "Fusion"
TRUNCATED_NOTE = "… [kırpıldı]"
DEFAULT_TITLE = "Fusion sohbeti"

_HEADING = re.compile(r"^(\s{0,3})(#{1,6})(?=\s)", re.MULTILINE)


def escape_headings(text: str) -> str:
    """Gövdedeki satır başı `#` başlıkları kaçır: `## Siz` yazan metin rol taklit edemesin."""
    return _HEADING.sub(r"\1\\\2", text)


def _shareable(messages: Sequence[Message]) -> list[Message]:
    """Dışa çıkacak mesajlar: sistem istemi ve harness notları dışarıda."""
    return [
        message
        for message in messages
        if message.role in ("user", "assistant", "tool")
        and not message.harness_note
        and (message.content.strip() or message.tool_calls)
    ]


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + TRUNCATED_NOTE


def _calls_block(calls: Sequence[ToolCall]) -> str:
    lines = [f"<details><summary>Araç çağrıları ({len(calls)})</summary>", ""]
    for call in calls:
        lines.append(f"- `{call.name}` {redact(_clip(call.arguments, TOOL_ARGS_CHARS))}")
    lines.extend(["", "</details>"])
    return "\n".join(lines)


_BACKTICK_RUN = re.compile(r"`{3,}")


def _fence_for(body: str) -> str:
    """Gövdedeki en uzun ``` dizisinden bir uzun çit: içerik çiti kapatıp dışarı çıkamaz."""
    longest = max((len(run) for run in _BACKTICK_RUN.findall(body)), default=2)
    return "`" * (longest + 1)


def _tool_block(message: Message) -> str:
    """Araç sonucu katlanmış ve çitli. Ölçüldü (31 Ekim): içerikteki ``` çiti kapatıyor,
    ardından gelen `## Siz` çit dışında rol taklit ediyordu; `name` de kaçışsızdı."""
    name = html_escape(message.name or "araç", quote=False)
    durum = "" if message.ok is None else (" · tamam" if message.ok else " · hata")
    body = escape_headings(redact(_clip(message.content.strip(), TOOL_OUTPUT_CHARS)))
    fence = _fence_for(body)
    head = f"<details><summary>Araç sonucu: {name}{durum}</summary>"
    return f"{head}\n\n{fence}text\n{body}\n{fence}\n\n</details>"


def _clean_title(title: str) -> str:
    """Başlık tek satır ve MASKELİ: ilk kullanıcı mesajından gelir, anahtar taşıyabilir."""
    return redact(" ".join(title.split())) or DEFAULT_TITLE


def export_markdown(messages: Sequence[Message], *, title: str = DEFAULT_TITLE) -> str:
    """Konuşmayı Markdown'a çevir. Araç çağrıları/sonuçları katlanmış ve kırpılmış."""
    parts = [f"# {_clean_title(title)}"]
    for message in _shareable(messages):
        if message.role == "tool":
            parts.append(_tool_block(message))
            continue
        heading = ROLE_USER if message.role == "user" else ROLE_ASSISTANT
        body = escape_headings(redact(message.content.strip()))
        section = f"## {heading}\n\n{body}" if body else f"## {heading}"
        if message.tool_calls:
            section += "\n\n" + _calls_block(message.tool_calls)
        parts.append(section)
    return "\n\n".join(parts) + "\n"


def export_json(messages: Sequence[Message], *, title: str = DEFAULT_TITLE) -> str:
    """Konuşmayı JSON'a çevir: aynı süzgeç ve maskeleme, yapı makine için."""
    rows: list[dict[str, object]] = []
    for message in _shareable(messages):
        row: dict[str, object] = {
            "rol": message.role,
            "metin": redact(_clip(message.content, TOOL_OUTPUT_CHARS))
            if message.role == "tool"
            else redact(message.content),
        }
        if message.tool_calls:
            row["arac_cagrilari"] = [
                {"ad": call.name, "argumanlar": redact(_clip(call.arguments, TOOL_ARGS_CHARS))}
                for call in message.tool_calls
            ]
        if message.role == "tool":
            row["arac"] = message.name
            row["ok"] = message.ok
        rows.append(row)
    payload = {"baslik": _clean_title(title), "mesajlar": rows}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def last_answer(messages: Sequence[Message], index: int = 1) -> str | None:
    """Sondan `index`. asistan cevabı (1 = en son); yoksa None. `/copy [N]` bunu kullanır."""
    answers = [
        message.content.strip()
        for message in messages
        if message.role == "assistant" and message.content.strip() and not message.harness_note
    ]
    if index < 1 or index > len(answers):
        return None
    # Pano da bir çıkış noktasıdır: cevaptaki anahtar olduğu gibi kopyalanmaz (31 Ekim).
    return redact(answers[-index])


def default_export_name(
    *, as_json: bool = False, ext: str = "", now: Callable[[], float] = time.time
) -> str:
    """`fusion-sohbet-YYYYMMDD-HHMM.<uzantı>` — saat enjekte edilebilir (testte sabit)."""
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(now()))
    suffix = ext or ("json" if as_json else "md")
    return f"fusion-sohbet-{stamp}.{suffix}"


def _indent_result(text: str) -> str:
    """Araç çıktısı: ilk satır `  ⎿  `, sonrakiler aynı hizada."""
    lines = text.splitlines() or [""]
    return "\n".join([f"  ⎿  {lines[0]}", *(f"     {line}" for line in lines[1:])])


def export_text(messages: Sequence[Message], *, title: str = DEFAULT_TITLE) -> str:
    """Konuşmayı düz metne çevir (Claude Code `/export`): roller işaretli, araçlar okunur."""
    parts = [_clean_title(title)]
    for message in _shareable(messages):
        if message.role == "tool":
            body = redact(_clip(message.content.rstrip(), TOOL_OUTPUT_CHARS))
            parts.append(_indent_result(body))
            continue
        body = redact(message.content.strip())
        if message.role == "user":
            parts.append("\n".join(f"> {line}" for line in body.splitlines()) or ">")
        elif body:
            parts.append(f"⏺ {body}")
        for call in message.tool_calls:
            args = redact(_clip(call.arguments, TOOL_ARGS_CHARS))
            parts.append(f"⏺ {call.name}({args})")
    return "\n\n".join(parts) + "\n"
