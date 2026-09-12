"""Hesap avatarı — emoji ya da kullanıcının seçtiği görsel.

Görsel hesabın KENDİ dizinine kopyalanır. Kaynak yola bağlı kalmak kırılgandı:
kullanıcı dosyayı taşıdığında ya da harici diski çıkardığında avatar kayboluyor
olurdu. Kopya küçüktür ve hesapla birlikte silinir.

Depoda `Account.avatar` tek bir metindir ve iki biçimden birini taşır:
emoji (kısa metin) ya da kopyalanmış dosyanın MUTLAK YOLU. Ayrım arayüzde yol
ayıracına bakılarak yapılır; ikinci bir alan açmak şemayı ve tüm çağıranları
değiştirmeyi gerektirirdi.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config.paths import account_config_dir

__all__ = ["AVATAR_MAX_BYTES", "AVATAR_SUFFIXES", "is_image_avatar", "store_avatar_image"]

#: Kabul edilen görsel uzantıları.
#
# Liste dar tutulur: avatar küçük bir simgedir, video ya da katmanlı belge
# değildir. `.svg` DIŞARIDADIR — betik taşıyabilen bir biçimi arayüze doğrudan
# gömmek gereksiz bir risk.
AVATAR_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})

#: Kopyalanacak en büyük dosya (bayt).
#
# 8 MB, telefonla çekilmiş bir fotoğrafı bile rahat alır; daha büyüğü avatar
# olarak anlamsızdır ve hesap dizinini boşuna şişirir.
AVATAR_MAX_BYTES = 8 * 1024 * 1024

#: Kopyanın hesap dizinindeki sabit adı (uzantı kaynaktan gelir).
_BASENAME = "avatar"


def is_image_avatar(value: str) -> bool:
    """Bu avatar bir dosya yolu mu, yoksa emoji mi?"""
    return "/" in value or "\\" in value


def store_avatar_image(account_id: str, source: str) -> str:
    """Seçilen görseli hesabın dizinine kopyala; kaydedilecek yolu döndür.

    Hata metinleri kullanıcıya gösterilir, bu yüzden ne yapması gerektiğini
    söylerler.
    """
    kaynak = Path(source).expanduser()
    if not kaynak.is_file():
        raise ValueError("Seçilen dosya bulunamadı.")
    uzanti = kaynak.suffix.lower()
    if uzanti not in AVATAR_SUFFIXES:
        kabul = ", ".join(sorted(AVATAR_SUFFIXES))
        raise ValueError(f"Avatar için desteklenen biçimler: {kabul}")
    if kaynak.stat().st_size > AVATAR_MAX_BYTES:
        raise ValueError(f"Avatar {AVATAR_MAX_BYTES // (1024 * 1024)} MB'tan büyük olamaz.")
    hedef_dizin = account_config_dir(account_id)
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    # Eski avatar kalmasın: her uzantıdan yalnız bir kopya tutulur, yoksa
    # png'den jpg'ye geçen kullanıcının eski dosyası dizinde öksüz kalırdı.
    for eski in AVATAR_SUFFIXES:
        (hedef_dizin / f"{_BASENAME}{eski}").unlink(missing_ok=True)
    hedef = hedef_dizin / f"{_BASENAME}{uzanti}"
    shutil.copy2(kaynak, hedef)
    return str(hedef)
