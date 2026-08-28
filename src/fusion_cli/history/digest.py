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
from datetime import UTC, datetime

from .models import HistorySource, SessionRef

#: Künyede gösterilecek en fazla kullanıcı mesajı.
MAX_LINES = 40
#: Künyedeki tek bir satırın en fazla uzunluğu.
LINE_BUDGET = 120
#: Künye taramasında aynı anda bellekte tutulacak tur sayısı.
SCAN_PAGE_SIZE = 100

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


@dataclass(frozen=True, slots=True)
class _ScanResult:
    """Sayfalı taramanın yalnızca künyeye gereken küçük sonucu."""

    secret_count: int
    turn_count: int
    user_lines: tuple[str, ...]
    has_more_user_lines: bool


def count_secrets(text: str) -> int:
    """Metindeki sır benzeri dizgileri say. İçeriği DEĞİŞTİRMEZ."""
    return sum(len(pattern.findall(text)) for pattern in _SECRET_PATTERNS)


def build_digest(source: HistorySource, ref: SessionRef, max_lines: int = MAX_LINES) -> Digest:
    """Bir oturumun deterministik künyesini üret."""
    scan = _scan_session(source, ref.session_id, max(max_lines, 0))

    lines = [
        f'<devralinan_oturum kaynak="{ref.source}" kimlik="{ref.session_id}">',
        f"başlık: {ref.title}",
        f"tarih: {_date_of(ref.updated_at)}",
        f"tur sayısı: {scan.turn_count}",
        "dokunulan dosyalar: güvenilir üstveri yok",
        "kullanıcının istekleri (sırayla):",
    ]
    lines.extend(scan.user_lines)
    if scan.has_more_user_lines:
        lines.append("  […daha fazlası var, read_session ile devamını oku…]")
    lines.append("</devralinan_oturum>")
    return Digest(text="\n".join(lines), secret_count=scan.secret_count)


def _scan_session(source: HistorySource, session_id: str, max_lines: int) -> _ScanResult:
    """Oturumun tamamını küçük sayfalarla tara; sayfaları elde tutma."""
    cursor = 0
    secret_count = 0
    user_lines: list[str] = []
    has_more = False
    while True:
        page = source.read(session_id, cursor=cursor, limit=SCAN_PAGE_SIZE)
        if not page:
            break
        for index, turn in enumerate(page):
            secret_count += count_secrets(turn.text)
            if turn.role == "user":
                if len(user_lines) < max_lines:
                    summary = " ".join(turn.text.split())[:LINE_BUDGET]
                    user_lines.append(f"  [{cursor + index}] {summary}")
                else:
                    has_more = True
        cursor += len(page)
        if len(page) < SCAN_PAGE_SIZE:
            break
    return _ScanResult(secret_count, cursor, tuple(user_lines), has_more)


def _date_of(updated_at: float) -> str:
    """Unix zamanını saat diliminden bağımsız ISO tarihe çevir."""
    if updated_at <= 0:
        return "bilinmiyor"
    return datetime.fromtimestamp(updated_at, tz=UTC).date().isoformat()
