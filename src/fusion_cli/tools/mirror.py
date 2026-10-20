"""Site aynalama — açık tarayıcı oturumuyla bir sayfayı kaynaklarıyla indir.

Neden tarayıcıyla ve neden ayrı bir araç:

`web_fetch` yalnızca HTML metni getirir; CSS, JS, görsel ve font gelmez, sayfa
yerelde çıplak açılır. Modelin sayfayı elle yeniden yazması ise bağlam penceresine
sığmaz — render edilmiş bir mağaza sayfası yüz binlerce karakterdir.

Aynalama tarayıcı oturumunu kullanır: şifre/giriş kapısı `browser_type` ile
geçildiyse aynalama da o oturumu görür. Sayfanın YÜKLEDİĞİ kaynaklar dinlenir,
diske yazılır ve HTML içindeki adresler yerel yollara çevrilir.

SINIRLARI AÇIKÇA BİLDİRİLİR: çalışma anında JavaScript ile çekilen veri, farklı
sayfalar ve sunucu tarafı davranış kopyalanmaz. Araç sonucunda bu yazılır ki model
"eksiksiz kopyaladım" demesin — ölçülen zarar tam olarak buydu.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

#: Aynalanacak kaynak türleri. HTML dışı her şey `assets/` altına düz yazılır.
MIRRORED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".css",
        ".js",
        ".mjs",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".svg",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
    }
)

#: Tek bir kaynağın kabul edilen en büyük boyutu (bayt). Devasa bir video ya da
#: kaynak haritası aynayı şişirir ve işe yaramaz.
MAX_ASSET_BYTES = 5_000_000
#: Aynalanacak en fazla kaynak sayısı. Sonsuz kaynak zinciri buradan kesilir.
MAX_ASSETS = 400
#: Yerel dosya adındaki karma uzunluğu: aynı adlı farklı kaynakları ayırır.
_HASH_LENGTH = 10

#: Yerel dosya adında güvenli olmayan karakterler.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class MirroredAsset:
    """Aynalanmış tek bir kaynak: uzak adresi ve yerel göreli yolu."""

    url: str
    local: str


def asset_local_path(url: str) -> str:
    """Bir kaynak adresini `assets/` altındaki KARARLI yerel yola çevir.

    Ad çakışmasını karma çözer: iki farklı CDN'den gelen `style.css` aynı dosyaya
    yazılamaz. Karma tam adresten üretilir, dolayısıyla aynı adres her koşuda aynı
    yerel yola düşer ve tekrar indirme gerekmez.
    """
    parsed = urlparse(url)
    ham = unquote(parsed.path).rsplit("/", 1)[-1] or "kaynak"
    temiz = _UNSAFE.sub("-", ham).strip("-") or "kaynak"
    # Uzantı korunur: tarayıcı yerel dosyayı uzantısından tanır.
    karma = hashlib.sha256(url.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    kok, nokta, uzanti = temiz.rpartition(".")
    return f"assets/{kok or temiz}-{karma}.{uzanti}" if nokta else f"assets/{temiz}-{karma}"


def is_mirrorable(url: str, content_type: str = "") -> bool:
    """Bu kaynak aynalanmalı mı? Uzantı ya da içerik türünden karar verilir.

    Sorgu dizesi (`?v=123`) uzantıyı gizler; bu yüzden içerik türü de kabul edilir.
    """
    if not url.startswith(("http://", "https://")):
        return False
    yol = unquote(urlparse(url).path).lower()
    if any(yol.endswith(uzanti) for uzanti in MIRRORED_SUFFIXES):
        return True
    tur = content_type.split(";", 1)[0].strip().lower()
    return tur.startswith(("image/", "font/")) or tur in {
        "text/css",
        "application/javascript",
        "text/javascript",
        "application/font-woff",
    }


def rewrite_links(html: str, assets: tuple[MirroredAsset, ...]) -> str:
    """HTML/CSS içindeki uzak adresleri yerel yollarla değiştir. Saf fonksiyon.

    Üç biçim aranır çünkü sayfalar üçünü de kullanır:
    `https://cdn/x.css`, `//cdn/x.css` (şemasız) ve `/x.css` (köke göreli).

    Uzun adres önce değiştirilir: kısa bir adres uzun bir adresin ÖNEKİ olabilir
    (`/a.css` ile `/a.css.map`) ve kısası önce uygulanırsa uzununu bozar.
    """
    sonuc = html
    for asset in sorted(assets, key=lambda item: len(item.url), reverse=True):
        parsed = urlparse(asset.url)
        yol = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        for bicim in (asset.url, f"//{parsed.netloc}{yol}", yol):
            if bicim:
                sonuc = sonuc.replace(bicim, asset.local)
    return sonuc


def mirror_summary(
    target: Path, assets: tuple[MirroredAsset, ...], skipped: int, truncated: bool
) -> str:
    """Aynalama sonucunu ve SINIRLARINI modele bildir.

    Sınırlar araç SONUCUNA yazılır: bu proje boyunca ölçülen davranış, modelin
    prompt kurallarını atlayıp araç sonucuna tepki verdiğidir. "Eksiksiz kopyaladım"
    demesini engelleyen tek şey burada yazandır.
    """
    satirlar = [
        f"ayna yazıldı: {target}",
        f"index.html + {len(assets)} kaynak (atlanan: {skipped})",
    ]
    if truncated:
        satirlar.append(f"UYARI: kaynak sınırına ({MAX_ASSETS}) ulaşıldı, kalanlar indirilmedi.")
    satirlar.append(
        "AYNANIN SINIRLARI — bunu 'eksiksiz kopya' olarak SUNMA:\n"
        "- Yalnızca BU sayfa aynalandı; sitenin diğer sayfaları indirilmedi.\n"
        "- Çalışma anında JavaScript ile çekilen veri (ürün listesi, sepet, arama) "
        "yerelde ÇALIŞMAZ; sunucu tarafı davranış kopyalanamaz.\n"
        "- Üçüncü parti betikler (analitik, ödeme, sohbet) yerelde hata verecektir.\n"
        "Kullanıcıya ne indiğini ve nelerin çalışmayacağını AÇIKÇA söyle. Görev "
        "'benzerini yap' ise aynayı REFERANS olarak kullan, teslim olarak değil."
    )
    return "\n".join(satirlar)
