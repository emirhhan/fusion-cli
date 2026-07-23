"""Görsel tema — renk ve simgelerin tek kaynağı.

Kod içine hex ya da Rich markup gömülmez. Renkler truecolor'dır; terminal
desteklemiyorsa Rich otomatik olarak 256 renge iner.
"""

from __future__ import annotations

ACCENT = "#FF8C42"
ACCENT_ALT = "#D6409F"
DIM = "#6B7280"
OK = "#3FB950"
WARN = "#D29922"
ERROR = "#F85149"
INFO = "#58A6FF"

#: Kullanıcı mesajı bandının zemini — koyu temada hafifçe ayrışır.
SURFACE = "#1B1F27"

ICON_OK = "✓"
ICON_ERROR = "✗"
ICON_DENIED = "⊘"
ICON_DONE = "✦"
ICON_STATUS = "›"
ICON_PROMPT = "❯"
ICON_ANSWER = "●"
