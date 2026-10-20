"""Proje kökünde bulunamayan dosyayı kullanıcının olağan klasörlerinde arar.

Kullanıcı projeyi bir klasörde açıp başka bir yerdeki (Belgeler, Masaüstü, İndirilenler)
dosyayı istediğinde küçük modeller kökten çıkmayı düşünmeyip aynı yolu tekrarlıyordu.
Dosya araçlarının "dosya yok" cevabına burada bulunan GERÇEK yollar eklenir.
"""

from __future__ import annotations

import os
from pathlib import Path

USER_FOLDERS = ("Documents", "Desktop", "Downloads")
MAX_MATCHES = 5
MAX_DEPTH = 5
MAX_VISITED_DIRS = 4000
_SKIPPED = frozenset({"node_modules", "__pycache__", "venv", "site-packages", "Library"})


def find_in_user_folders(
    name: str, home: Path | None = None, limit: int = MAX_MATCHES
) -> tuple[Path, ...]:
    """`name` adlı dosyaları kullanıcı klasörlerinde ara (sınırlı derinlik ve sayı)."""
    if not name or "/" in name or "\\" in name:
        return ()
    base = home if home is not None else Path.home()
    hedef = name.casefold()
    bulunan: list[Path] = []
    gezilen = 0
    for klasor in USER_FOLDERS:
        kok = base / klasor
        if not kok.is_dir():
            continue
        for dizin, alt, dosyalar in os.walk(kok):
            gezilen += 1
            derinlik = len(Path(dizin).relative_to(kok).parts)
            alt[:] = sorted(
                a
                for a in alt
                if not a.startswith(".") and a not in _SKIPPED and derinlik < MAX_DEPTH
            )
            for dosya in sorted(dosyalar):
                if dosya.casefold() == hedef:
                    bulunan.append(Path(dizin) / dosya)
                    if len(bulunan) >= limit:
                        return tuple(bulunan)
            if gezilen >= MAX_VISITED_DIRS:
                return tuple(bulunan)
    return tuple(bulunan)


#: Eşleşme çıkmayınca modele söylenen son çare: gizli ve bağımlılık klasörleri
#: kullanıcı onayı olmadan taranmaz. `ask_user` onay kipinden bağımsız çalışır
#: (otomatik, düzenlemeleri kabul, plan, izinleri atla); bu yüzden her kipte sorulur.
HIDDEN_FOLDERS_ASK = (
    " Belgeler, Masaüstü ve İndirilenler'de bu ada sahip dosya yok. Dosya zaten var "
    "olmalıysa son çare gizli (.ile başlayan) ve bağımlılık (node_modules, venv) "
    "klasörleridir: orada aramadan ÖNCE ask_user ile kullanıcıya aranıp aranmayacağını "
    "sor; cevabı bekle, varsayma. Yeni dosya oluşturuyorsan bu soruyu atla."
)


def user_folder_hint(name: str, home: Path | None = None) -> str:
    """Hata mesajına eklenecek cümle: bulunan yollar ya da gizli klasör sorusu."""
    bulunan = find_in_user_folders(name, home)
    if not bulunan:
        return HIDDEN_FOLDERS_ASK if name else ""
    yollar = ", ".join(str(yol) for yol in bulunan)
    if len(bulunan) == 1:
        return (
            f" Aynı adlı dosya proje dışında bulundu: {yollar}. "
            "Kullanıcı bunu kastediyorsa bu mutlak yolu kullan."
        )
    return (
        f" Aynı adlı dosyalar proje dışında bulundu: {yollar}. Hangisi olduğundan emin "
        "değilsen ask_user ile kullanıcıya sor."
    )
