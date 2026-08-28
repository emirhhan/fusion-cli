"""Oturum künyesi: devralmadan önce basılan ucuz triyaj özeti.

Künye DETERMİNİSTİKTİR — model çağrısı içermez, aynı girdi her zaman aynı çıktıyı
verir. Amacı oturumun tamamını bağlama yüklemek değil, ajana NEREYE bakacağını
söylemektir; ayrıntı `read_session` ile çekilir.

Yalnızca kullanıcı mesajları listelenir: ajan cevapları uzundur ve triyaj için
değeri düşüktür. İşin ne olduğunu kullanıcının kendi cümleleri anlatır.

Sırlar SAYILIR ama MASKELENMEZ. Bu bilinçli bir üründür kararıdır: maskeleme
devralınan bağlamı sessizce bozabilir. Sayım yalnızca kullanıcıyı uyarmak içindir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import HistorySource, SessionRef

#: Künyede gösterilecek en fazla kullanıcı mesajı.
MAX_LINES = 40
#: Künyedeki tek bir satırın en fazla uzunluğu.
LINE_BUDGET = 120
#: Künye üretilirken kaynaktan çekilecek en fazla tur.
SCAN_LIMIT = 400

#: Sır ARAMA desenleri. Amaç maskelemek değil saymaktır; bu yüzden geniş tutulur,
#: yanlış pozitif kabul edilebilir — kullanıcıya "bak" demek yeterlidir.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(sk-[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,})"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"\b[A-Z][A-Z0-9_]*_(KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S{8,}"),
    re.compile(r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY"),
)


@dataclass(frozen=True, slots=True)
class Digest:
    """Bağlama girecek künye metni ve bulunan sır sayısı."""

    text: str
    secret_count: int


def count_secrets(text: str) -> int:
    """Metindeki sır benzeri dizgileri say. İçeriği DEĞİŞTİRMEZ."""
    return sum(len(pattern.findall(text)) for pattern in _SECRET_PATTERNS)


def build_digest(source: HistorySource, ref: SessionRef, max_lines: int = MAX_LINES) -> Digest:
    """Bir oturumun deterministik künyesini üret."""
    turns = source.read(ref.session_id, cursor=0, limit=SCAN_LIMIT)
    secret_count = sum(count_secrets(turn.text) for turn in turns)

    lines = [
        f'<devralinan_oturum kaynak="{ref.source}" kimlik="{ref.session_id}">',
        f"başlık: {ref.title}",
        f"tur sayısı: {len(turns)}",
        "kullanıcının istekleri (sırayla):",
    ]
    shown = 0
    for index, turn in enumerate(turns):
        if turn.role != "user":
            continue
        if shown >= max_lines:
            lines.append("  […daha fazlası var, read_session ile devamını oku…]")
            break
        summary = " ".join(turn.text.split())[:LINE_BUDGET]
        lines.append(f"  [{index}] {summary}")
        shown += 1
    lines.append("</devralinan_oturum>")
    return Digest(text="\n".join(lines), secret_count=secret_count)
