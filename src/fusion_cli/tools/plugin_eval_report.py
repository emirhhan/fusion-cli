"""`plugin eval` kendi içinde yeterli HTML raporu (Claude `--report <yol>`, #380).

Puanlar, istemler ve değerlendirici kararları tek dosyada; dış kaynak yok, tüm metin kaçışlıdır.
Varsayılan yer sonuç klasöründeki `report.html`; `--report <yol>` başka yere yazar. Claude'un
raporu claude.ai'de yayımlaması Fusion'da yoktur (claude.ai hesabı gerektirir).
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
from pathlib import Path

from .plugin_eval import EvalCase

_STYLE = """
:root{--bg:#fbfaf7;--fg:#1d1b18;--muted:#6b665c;--ok:#1f7a4d;--bad:#b3261e;--line:#e4dfd4}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece8df;--muted:#a39d90;
--ok:#5fc48f;--bad:#f2867c;--line:#2e2b26}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui;margin:0;
padding:24px 16px;max-width:960px;margin-inline:auto}
h1{font-size:22px;margin:0 0 4px}.muted{color:var(--muted)}table{border-collapse:collapse;
width:100%;margin:12px 0}td,th{border-bottom:1px solid var(--line);padding:6px 8px;
text-align:left;vertical-align:top}.ok{color:var(--ok)}.bad{color:var(--bad)}
pre{white-space:pre-wrap;background:transparent;border:1px solid var(--line);padding:8px}
details{margin:8px 0}
"""


def _score(value: object, threshold: float) -> str:
    number = float(value) if isinstance(value, int | float) else 0.0
    css = "ok" if number >= threshold else "bad"
    return f'<span class="{css}">{number:.2f}</span>'


def _graders(run: Mapping[str, object]) -> str:
    rows = run.get("graders")
    items = rows if isinstance(rows, list) else []
    cells = "".join(
        f"<tr><td>{escape(str(g.get('name')))}</td><td>{escape(str(g.get('type')))}</td>"
        f"<td>{float(g.get('score') or 0):.2f}</td>"
        f"<td>{'' if g.get('scored', True) else 'gösterge'}</td></tr>"
        for g in items
        if isinstance(g, dict)
    )
    return (
        f"<table><tr><th>Değerlendirici</th><th>Tür</th><th>Puan</th><th></th></tr>{cells}</table>"
    )


def _case(row: Mapping[str, object], case: EvalCase | None, threshold: float) -> str:
    parts = [f"<h2>{escape(str(row.get('name')))}</h2>"]
    if case is not None:
        parts.append(f"<details><summary>İstem</summary><pre>{escape(case.prompt)}</pre></details>")
    for arm in ("with", "without"):
        data = row.get(arm)
        if not isinstance(data, dict):
            continue
        runs = data.get("runs") if isinstance(data.get("runs"), list) else []
        parts.append(f"<p><b>{arm}</b> {_score(data.get('score'), threshold)}</p>")
        for index, run in enumerate(runs or [], 1):
            if isinstance(run, dict):
                parts.append(
                    f"<details><summary>Koşu {index}: {_score(run.get('score'), threshold)}"
                    f"</summary>{_graders(run)}</details>"
                )
    if "delta" in row:
        parts.append(f"<p>Δ {float(row.get('delta') or 0):+.2f}</p>")  # type: ignore[arg-type]
    return "<section>" + "".join(parts) + "</section>"


def render_report(
    result: Mapping[str, object], cases: tuple[EvalCase, ...], *, threshold: float
) -> str:
    by_name = {case.name: case for case in cases}
    raw = result.get("cases")
    rows: list[object] = list(raw) if isinstance(raw, list) else []
    body = "".join(
        _case(row, by_name.get(str(row.get("name"))), threshold)
        for row in rows
        if isinstance(row, dict)
    )
    title = escape(str(result.get("plugin") or "eval"))
    meta = (
        f"ablation {escape(str(result.get('ablation')))} · maliyet "
        f"${float(result.get('costUsd') or 0):.4f}"  # type: ignore[arg-type]
    )
    return (
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Eval raporu</title><style>{_STYLE}</style></head><body>"
        f'<h1>{title}</h1><p class="muted">{meta}</p>{body}</body></html>\n'
    )


def write_report(path: Path, html: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, "utf-8")
    return path
