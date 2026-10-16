"""Belirsiz YENİ proje isteğinde koda başlamadan seçenekli soru teşviki.

Claude bu kararı modelin kendi muhakemesiyle verir; ücretsiz modellerde sistem
talimatındaki kural yetmedi. Ölçüldü (26 Eylül, gemini_web): "Müşterilerin
sipariş numarasıyla kargo durumunu sorgulayabileceği bir web uygulaması yap."
isteğinde model teknolojiyi ve veri kaynağını sormadan Flask + uydurma
`orders.json` ile 8,5 dakika kodladı; asıl veri kaynağı (mağaza) hiç sorulmadı.

Not DAR tutulur: yalnız soru sorulabilen oturumun ilk turunda, proje dosyası
olmayan bir klasörde ve kısa bir "uygulama/site/proje yap" isteğinde eklenir.
Var olan projede ya da ayrıntılı şartnamede kararlar zaten verilmiştir.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Kararları içermeyen kısa istek sınırı (karakter). Ölçülen belirsiz istekler
#: 25-95 karakterdi; kararları sıralayan şartnameler 250+ karakter. Sınır ikisinin
#: arasındadır: uzun ama belirsiz istek notu kaçırır — bu, gereksiz soru sormaktan
#: daha ucuz bir hatadır (kullanıcı ayrıntı vermişse sormak onu yorar).
MAX_UNDERSPECIFIED_CHARS = 200

_BUILD = re.compile(
    r"\b(?:yap|oluştur|olustur|kur|geliştir|gelistir|hazırla|hazirla|tasarla|"
    r"build|create|make)\w*",
    re.IGNORECASE,
)
_PROJECT = re.compile(
    r"(?:uygulama|app\b|site|proje|panel|dashboard|bot\w*|oyun|api\b|sistem|platform|"
    r"mağaza|magaza|e-?ticaret)",
    re.IGNORECASE,
)
# Uzunluk tek başına kritik veri kaynağı eksikliğini gizleyemez.
_DATA_REQUIRED = re.compile(r"sipariş|siparis|müşteri|musteri|kargo|stok|orders?|customers?", re.I)
_SOURCE_GIVEN = re.compile(
    r"shopify|woocommerce|postgres|sqlite|\bcsv\b|\bexcel\b|\bmdx\b|veriyi.+(?:oku|al)", re.I
)
_TECH_GIVEN = re.compile(r"\breact\b|next\.js|\bvue\b|\bdjango\b|\bflask\b|\bflutter\b", re.I)

#: Klasörde bunlardan biri varsa var olan bir projede çalışılıyordur.
_PROJECT_MARKERS = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "index.html",
    "manage.py",
    "project.godot",
)

CLARIFY_NOTE = (
    "Bu, ayrıntısı verilmemiş YENİ bir proje isteği. Kod yazmadan ÖNCE `ask_user` ile "
    "sonucu en çok değiştiren TEK kararı sor (ör. veri nereden gelecek, hangi teknoloji, "
    "kapsam). 2-4 somut seçenek ver, her birine kısa açıklama yaz ve `recommended` ile "
    "önerini işaretle. Cevabı aldıktan sonra sormadan uygula."
)


def clarification_hint(task: str, root: Path, *, can_ask: bool, first_turn: bool) -> str | None:
    """Notu döndür; koşullar tutmuyorsa `None`."""
    metin = task.strip()
    if not (can_ask and first_turn):
        return None
    if not (_BUILD.search(metin) and _PROJECT.search(metin)):
        return None
    if any((root / marker).exists() for marker in _PROJECT_MARKERS):
        return None
    missing_source = bool(_DATA_REQUIRED.search(metin) and not _SOURCE_GIVEN.search(metin))
    if missing_source:
        return CLARIFY_NOTE
    if _TECH_GIVEN.search(metin) or len(metin) > MAX_UNDERSPECIFIED_CHARS:
        return None
    return CLARIFY_NOTE
