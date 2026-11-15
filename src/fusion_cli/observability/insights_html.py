"""`fusion insights`: kullanım günlüğünden tek dosya HTML rapor (Claude Code `/insights`; P-056).

Bağımlılık yok, dış kaynak yok: rapor çevrimdışı açılır. Renkler açık/koyu temaya
`prefers-color-scheme` ile uyar. Metinler Türkçe. İstem metni günlükte olmadığı için
raporda da yoktur; yalnız sayılar.
"""

from __future__ import annotations

import html
import time
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from .usage_log import KIND_MODEL, UsageBucket, UsageRecord, UsageSummary

_STYLE = """
:root { --bg:#f7f5f0; --ink:#1d1b17; --muted:#6b665c; --card:#fffdf8; --line:#e4dfd3;
        --accent:#b4572a; --bar:#d9a066; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16140f; --ink:#f1ece2; --muted:#a39c8e; --card:#1f1c16; --line:#2d2921;
          --accent:#e38a55; --bar:#8a5a2e; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font: 15px/1.5 "Iowan Old Style", "Palatino", Georgia, serif; padding: 32px 16px 64px; }
main { max-width: 920px; margin: 0 auto; }
h1 { font-size: clamp(1.8rem, 1.2rem + 2vw, 2.6rem); margin: 0 0 4px; letter-spacing:-0.01em; }
.sub { color: var(--muted); margin: 0 0 28px; }
.grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap:12px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:14px;
        padding:14px 16px; }
.tile b { display:block; font-size:1.5rem; font-variant-numeric: tabular-nums; }
.tile span { color:var(--muted); font-size:.85rem; }
section { margin-top: 32px; }
h2 { font-size:1.15rem; margin:0 0 10px; color:var(--accent); font-weight:600;
     font-family: ui-sans-serif, system-ui, sans-serif; }
table { width:100%; border-collapse: collapse; background:var(--card); border:1px solid var(--line);
        border-radius:12px; overflow:hidden; }
th, td { text-align:left; padding:8px 12px; border-top:1px solid var(--line);
         font-variant-numeric: tabular-nums; }
th { background: transparent; color: var(--muted); font-weight:600; font-size:.8rem;
     text-transform: uppercase; letter-spacing:.05em; border-top:0; }
td.num, th.num { text-align:right; }
.bar { height:8px; background:var(--bar); border-radius:4px; }
.days { display:grid; grid-template-columns: repeat(auto-fill, minmax(26px,1fr)); gap:4px;
        align-items:end; height:120px; }
.day { background:var(--bar); border-radius:3px 3px 0 0; position:relative; }
.day:hover::after { content: attr(data-label); position:absolute; bottom:100%; left:50%;
     transform:translateX(-50%); background:var(--ink); color:var(--bg); font-size:.7rem;
     padding:2px 6px; border-radius:4px; white-space:nowrap; }
footer { margin-top:40px; color:var(--muted); font-size:.85rem; }
"""


def _esc(value: object) -> str:
    return html.escape(str(value))


def _money(value: float) -> str:
    return f"${value:.4f}"


def _rows(
    headers: tuple[str, ...], rows: Iterable[tuple[object, ...]], *, numeric_from: int
) -> str:
    head = "".join(
        f'<th class="{"num" if index >= numeric_from else ""}">{_esc(name)}</th>'
        for index, name in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"num" if index >= numeric_from else ""}">{_esc(cell)}</td>'
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _daily(
    records: Iterable[UsageRecord], *, now: float, days: int
) -> list[tuple[str, UsageBucket]]:
    buckets: dict[str, UsageBucket] = defaultdict(UsageBucket)
    for record in records:
        if record.tur != KIND_MODEL or now - record.ts > days * 86400.0:
            continue
        key = datetime.fromtimestamp(record.ts).strftime("%Y-%m-%d")
        buckets[key].add(record)
    return sorted(buckets.items())


def render_insights(
    summary: UsageSummary,
    records: Iterable[UsageRecord],
    *,
    now: float | None = None,
    days: int = 30,
    title: str = "Fusion kullanım raporu",
) -> str:
    """Özet + günlük kayıtlardan tam HTML belgesi döndür."""
    now = time.time() if now is None else now
    items = tuple(records)
    window_bucket = next(
        (bucket for label, bucket in summary.windows if label == summary.window_label),
        summary.windows[-1][1],
    )
    daily = _daily(items, now=now, days=days)
    peak = max((bucket.usage.total_tokens for _, bucket in daily), default=1) or 1
    tiles = (
        (f"{window_bucket.calls:,}", "model çağrısı"),
        (f"{window_bucket.usage.total_tokens:,}", "token"),
        (_money(window_bucket.usage.cost_usd), "tahmini maliyet"),
        (str(len(daily)), "aktif gün"),
    )
    tiles_html = "".join(
        f"<div class='tile'><b>{_esc(a)}</b><span>{_esc(b)}</span></div>" for a, b in tiles
    )
    days_html = "".join(
        f'<div class="day" style="height:{max(4, int(100 * bucket.usage.total_tokens / peak))}%" '
        f'data-label="{_esc(day)} · {bucket.usage.total_tokens:,} token · '
        f'{_money(bucket.usage.cost_usd)}"></div>'
        for day, bucket in daily
    )
    windows_table = _rows(
        ("Pencere", "Çağrı", "Girdi", "Çıktı", "Maliyet"),
        (
            (
                label,
                bucket.calls,
                f"{bucket.usage.prompt_tokens:,}",
                f"{bucket.usage.completion_tokens:,}",
                _money(bucket.usage.cost_usd),
            )
            for label, bucket in summary.windows
        ),
        numeric_from=1,
    )
    actors = _rows(
        ("Kaynak", "Çağrı", "Token", "Maliyet"),
        (
            (row.label, row.calls, f"{row.tokens:,}", _money(row.cost_usd))
            for row in summary.by_actor
        ),
        numeric_from=1,
    )
    models = _rows(
        ("Model", "Çağrı", "Token", "Maliyet"),
        (
            (row.label, row.calls, f"{row.tokens:,}", _money(row.cost_usd))
            for row in summary.by_model
        ),
        numeric_from=1,
    )
    mcp = _rows(("MCP sunucusu", "Araç çağrısı"), summary.mcp_calls, numeric_from=1)
    skills = _rows(("Beceri", "Yükleme"), summary.skills, numeric_from=1)
    generated = datetime.fromtimestamp(now).strftime("%d.%m.%Y %H:%M")
    empty_days = "<p class='sub'>Bu pencerede kayıt yok.</p>"
    footer = (
        "Fusion kullanım günlüğünden üretildi; istem metni ya da araç çıktısı içermez. "
        "Maliyetler sağlayıcının bildirdiği tahminlerdir."
    )
    head = (
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    )
    return f"""<!doctype html>
<html lang="tr"><head>{head}
<title>{_esc(title)}</title><style>{_STYLE}</style></head>
<body><main>
<h1>{_esc(title)}</h1>
<p class="sub">{_esc(summary.window_label)} · {generated} · {summary.record_count:,} kayıt</p>
<div class="grid">{tiles_html}</div>
<section><h2>Günlük token</h2><div class="days">{days_html or empty_days}</div></section>
<section><h2>Pencereler</h2>{windows_table}</section>
<section><h2>Kim harcadı</h2>{actors}</section>
<section><h2>Modeller</h2>{models}</section>
<section><h2>MCP sunucuları</h2>{mcp}</section>
<section><h2>Beceriler</h2>{skills}</section>
<footer>{footer}</footer>
</main></body></html>
"""
