"""OAuth dönüşünde kullanıcının tarayıcıda gördüğü sayfa.

Eskiden stilsiz tek satırdı (`<h1>Fusion</h1><p>…</p>`); kullanıcı "boş ve
kalitesiz" buldu. Sayfa Fusion'ın koyu yüzeyini, yazı tipini ve durum rengini
kullanır; dış kaynak yüklemez (dönüş sunucusu tek yanıt verip kapanır).
"""

from __future__ import annotations

from html import escape

_ICON_OK = (
    '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" '
    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="m5 12.5 4.5 4.5L19 7.5"/></svg>'
)
_ICON_ERROR = (
    '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" '
    'stroke-width="2.4" stroke-linecap="round" aria-hidden="true">'
    '<path d="M7 7l10 10M17 7 7 17"/></svg>'
)

_STYLE = """
:root { color-scheme: dark; --bg:#0d0f12; --card:#16191e; --line:#262a31; --text:#eef0f3;
  --muted:#9aa1ab; --ok:#4ade80; --err:#f87171; }
@media (prefers-color-scheme: light) { :root { color-scheme: light; --bg:#f4f5f7;
  --card:#fff; --line:#e3e5e9; --text:#15171a; --muted:#5d636c; --ok:#16a34a; --err:#dc2626; } }
* { box-sizing: border-box; }
body { margin:0; min-height:100vh; display:grid; place-items:center; padding:24px;
  background:var(--bg); color:var(--text);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; }
main { width:min(420px,100%); background:var(--card); border:1px solid var(--line);
  border-radius:18px; padding:32px 28px 26px; text-align:center;
  box-shadow:0 24px 60px rgb(0 0 0 / 28%); }
.icon { width:56px; height:56px; margin:0 auto 18px; border-radius:50%; display:grid;
  place-items:center; }
.ok .icon { color:var(--ok); background:color-mix(in srgb,var(--ok) 14%,transparent); }
.error .icon { color:var(--err); background:color-mix(in srgb,var(--err) 14%,transparent); }
.brand { font-size:13px; font-weight:600; letter-spacing:.02em;
  color:var(--muted); margin:0 0 6px; }
h1 { font-size:20px; margin:0 0 8px; }
p { margin:0; color:var(--muted); }
small { display:block; margin-top:22px; color:var(--muted); font-size:12px; }
"""


def callback_page(*, ok: bool, title: str, message: str) -> str:
    """Tam HTML belgesi; metinler kaçışlanır."""
    kind = "ok" if ok else "error"
    icon = _ICON_OK if ok else _ICON_ERROR
    hint = "Bu sekmeyi kapatıp Fusion'a dönebilirsin." if ok else "Fusion'a dönüp yeniden dene."
    return (
        "<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Fusion · {escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main class='{kind}' role='status'><div class='icon'>{icon}</div>"
        f"<p class='brand'>Fusion</p><h1>{escape(title)}</h1><p>{escape(message)}</p>"
        f"<small>{escape(hint)}</small></main></body></html>"
    )
