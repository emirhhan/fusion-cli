"""İsteğin türüne göre tura eklenen kısa yönlendirmeler (önizleme, kapsam, benzetme).

Sistem talimatındaki genel kural ücretsiz modellerde yetmedi; ölçülen iki davranış
için isteğe ÖZEL not eklenir (bkz. `clarify` — aynı desen).

Ölçüldü (2 Ekim 2026, "sneaksup" sohbeti):

1. "Nasıl önizleyebilirim?" / "ekstra bir şey kurmadan önizlememi sağla" isteğine
   model MySQL + Docker rehberi yazdı, sonra açmadığı bir `preview.html` bıraktı.
2. "sneaksup.com'un birebir kopyası, her sayfası ve eklentisiyle gerçek çalışan
   e-ticaret" isteğinde model 10 dakikada 17 dosyalık bir tema iskeleti yazıp
   "✓ Doğrulandı" dedi; işin büyüklüğünü ve neyin yapılmadığını hiç söylemedi.
3. Aynı istekte (5. kabul koşusu) `site_design` araç defterindeydi ama model onu hiç
   çağırmadı; siteyi `browser_open` ile 15 kez gezip tasarımı yine tahmin etti.
"""

from __future__ import annotations

import re

_PREVIEW = re.compile(
    r"önizle|onizle|önizleme|görüntüle|goruntule|\bgöster\b|\bgoster\b|görmek ist|"
    r"nasıl (?:aç|çalıştır|gör)|\bçalıştır\b|ayağa kaldır|localhost|"
    r"\bpreview\b|\bshow me\b|\brun it\b|\bopen it\b",
    re.IGNORECASE,
)
PREVIEW_NOTE = (
    "Kullanıcı sonucu GÖRMEK istiyor. Kurulum rehberi ya da komut listesi yazma; "
    "start_preview ile projeyi çalıştır (gereken kurulumu o yapar), sonra adresi ve "
    "ekran görüntüsünde gördüğün durumu 2-3 cümlede söyle. Ayrı bir önizleme dosyası "
    "(preview.html gibi) uydurma; asıl projeyi çalıştır."
)

_BIG_SCOPE = re.compile(
    r"birebir|bire bir|aynısı|aynisi|kopyası|klon|clone|her sayfa|tüm sayfa|bütün sayfa|"
    r"her eklenti|tüm eklenti|gerçek çalışan|tam çalışan|e-?ticaret sitesi|"
    r"production|canlıya|hostinge",
    re.IGNORECASE,
)
#: Bu kadar ve üstü kapsam işareti taşıyan istek "çok büyük iş" sayılır. Ölçülen
#: sneaksup isteği 5 işaret taşıyordu; tek işaret ("e-ticaret sitesi") sıradan istektir.
BIG_SCOPE_MIN_SIGNALS = 2
SCOPE_NOTE = (
    "Bu istek tek turda bitmeyecek kadar BÜYÜK. Şöyle çalış: (1) önce 3-6 maddelik bir "
    "aşama planı yaz (todo listesi) ve bu turda hangi ÇALIŞAN sürümü teslim edeceğini "
    "söyle; (2) o ilk aşamayı uçtan uca bitir — çalışan site, örnek içerik, start_preview "
    "ile açılıp görülmüş; (3) kapanışta yapılanı ve kalan aşamaları açıkça listele, "
    "yapılmayanı yapılmış gibi sunma."
)

_URL = re.compile(
    r"https?://[^\s)>\]]+|\b(?:www\.)?[a-z0-9-]+\.(?:com|net|org|io|co|app|dev)(?:\.[a-z]{2})?\b"
)
_LOOKALIKE = re.compile(
    r"benze|birebir|bire bir|aynısı|aynisi|aynı olacak|ayni olacak|kopya|klon|gibi (?:ol|yap|dur)|"
    r"\bclone\b|\bcopy of\b|look(?:s)? like|similar to|same as",
    re.IGNORECASE,
)
DESIGN_NOTE = (
    "Kullanıcı VAR OLAN bir siteye benzeyen site istiyor. Tasarımı TAHMİN ETME ve sayfaları "
    "tek tek gezme: ilk iş olarak site_design(url) çağır. O araç yazı tiplerini, renkleri, "
    "ölçüleri, sayfa bölümlerini, ürünleri ve görselleri ölçüp projeye indirir "
    "(tasarim-kaynak/). Sonra o ölçüleri ve indirilen dosyaları AYNEN kullan (font dosyası, "
    "renk, boyut, bölüm sırası, ürün adı/fiyatı/görseli). start_preview her çağrıda sayfanı "
    "kaynakla aynı ölçümle karşılaştırıp KAYNAKLA FARKLAR listesi verir: liste boşalana "
    "kadar düzeltip yeniden çağır (ürün sayfası için `page` ver). Kapanışta "
    "kullanıcıya söyle: logo ve ürün görselleri başka markaya ait, yerel çalışma için "
    "alındı; siteyi yayına almadan önce kendi içerikleriyle değiştirmeli."
)


def preview_hint(task: str, *, available: bool) -> str | None:
    if not available or _PREVIEW.search(task) is None:
        return None
    return PREVIEW_NOTE


def scope_hint(task: str) -> str | None:
    signals = {match.group(0).lower() for match in _BIG_SCOPE.finditer(task)}
    return SCOPE_NOTE if len(signals) >= BIG_SCOPE_MIN_SIGNALS else None


def design_hint(task: str, *, available: bool) -> str | None:
    """İstek bir adres VE benzerlik sözü taşıyorsa ölçüm aracına yönlendir."""
    if not available or _URL.search(task) is None or _LOOKALIKE.search(task) is None:
        return None
    return DESIGN_NOTE
