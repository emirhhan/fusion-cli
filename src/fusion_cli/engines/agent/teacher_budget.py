"""Öğretmen çağrı bütçesi — saatlik, kullanıcı veri dizininde (Faz 4, Görev 4).

Sınıra ulaşınca YENİ bir `ask_teacher` çağrısı YAPILMADAN ÖNCE kullanıcıya/modele
söylenir (araç ağa hiç çıkmaz) — CAPTCHA/insan-doğrulama riskini KASITLI olarak
TETİKLEMEDEN, yalnız MEVCUT ölçümden türetilmiş ihtiyatlı bir üst sınırdır.

Sayı UYDURULMADI. `providers/web_browser.py`'deki `ConversationPacer` (mevcut,
ölçülmüş, Faz 4'ten önce yazılmıştı) şunu belgeliyor:

- Kova: 3 patlama hakkı + 30 saniyede bir yenilenen 1 hak
  (`NEW_CONVERSATION_BURST`, `NEW_CONVERSATION_INTERVAL_S`) → sürekli
  çalıştırılırsa saatte azami 120 YENİ sohbet.
- Ölçüm (13 Eylül, kullanıcı makinesi): birkaç dakika içinde ~14 yeni sohbet
  isteği sağlayıcı tarafında BOT davranışı sayılıp
  `modal-conversation-history-rate-limit` uyguladı — sürekliye yayılırsa bu
  saatte ~168 isteğe denk gelir.

`ask_teacher` her çağrıda YENİ bir öğretmen sohbeti açar (brief her seferinde
farklıdır, devam eden bir sohbeti SÜRDÜRMEZ) — yani bu pacer'ın gördüğü aynı
"yeni sohbet" trafiğine dahildir. Saatlik 60 sınırı: pacer'ın azami hızının
(120/sa) TAM YARISI ve ölçülen tehlike eşiğinin (~168/sa) belirgin altında;
ayrıca kullanıcının istediği "saatte 25'in üstü" ölçütünü karşılar
(22 Eylül, plan §6.6 kararı — kasıtlı CAPTCHA testi YAPILMADI, güvenli yol
seçildi).

Sayaç dosyası PROJE İÇİNE yazılmaz: Ölçüldü (30 Ekim): `.fusion/ogretmen-butce.json`
deneme projesinde `git status`a düşüp commit'e karıştı. Sayaç kullanıcı veri
dizininde (`user_data_dir()/ogretmen-butce/`), proje köküne bağlı bir anahtarla
tutulur; eski konumdaki dosya ilk kontrolde okunup buraya taşınır.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from ...config.paths import user_data_dir

#: Kova ile AYNI mantıkta ama çok daha kaba bir üst sınır — bkz. modül docstring'i.
HOURLY_LIMIT = 60
# Öğretmen protokolü planının üst sınırı: ilk plan, bir biçim düzeltmesi,
# takılmada danışma, son denetim ve düzeltme denetimi beş çağrı yapabilir.
TURN_LIMIT = 5
WINDOW_S = 3600.0
#: Eski (proje içi) konum — yalnız bir kez okunup taşınır, sonra silinir.
LEGACY_BUDGET_PATH = ".fusion/ogretmen-butce.json"
#: Kullanıcı veri dizini altındaki sayaç klasörü.
BUDGET_DIR_NAME = "ogretmen-butce"
_KEY_HASH_LEN = 16


@dataclass(frozen=True, slots=True)
class BudgetCheck:
    """Bir bütçe kontrolünün sonucu."""

    allowed: bool
    #: Bu pencerede harcanan (kontrol İZİN VERDİYSE +1 dahil) çağrı sayısı.
    used: int
    limit: int
    #: Pencerenin sıfırlanmasına kalan saniye.
    reset_in_s: float


def budget_file(root: Path) -> Path:
    """Bir projenin sayaç dosyası: `user_data_dir()/ogretmen-butce/<klasör>-<kök özeti>.json`.

    Anahtar proje kökünün çözümlenmiş yolundan türer; aynı adlı iki klasör karışmaz.
    """
    cozulmus = str(root.resolve())
    ozet = hashlib.sha256(cozulmus.encode("utf-8")).hexdigest()[:_KEY_HASH_LEN]
    ad = re.sub(r"[^a-zA-Z0-9_.-]+", "-", root.resolve().name).strip("-._") or "proje"
    return user_data_dir() / BUDGET_DIR_NAME / f"{ad}-{ozet}.json"


def check_and_spend(
    root: Path, *, now: float, limit: int = HOURLY_LIMIT, window_s: float = WINDOW_S
) -> BudgetCheck:
    """Bu saatlik pencerede hak var mı kontrol et; VARSA harca (dosyaya yaz).

    Dosya bozuksa ya da okunamıyorsa sıfırdan başlanır — bütçe dosyası bir
    GÜVENLİK sınırı değildir, en kötü ihtimalle bir pencere fazladan sıfırlanır.
    """
    hedef = budget_file(root)
    mevcut = _oku(hedef)
    mevcut = _eski_konumu_tasi(root, hedef, mevcut)
    if mevcut is None or now - mevcut[0] >= window_s:
        # Dosya yok/bozuk YA DA pencere dolmuş: yeni pencere ŞİMDİ başlar.
        # `pencere_baslangic=0.0` gibi bir nöbetçi değer KULLANILMAZ — o,
        # gerçek epoch zamanında hep "pencere dolmuş" sonucunu VERİRDİ ama bu
        # örtük bir varsayımdır (yalnızca `now` her zaman `window_s`'ten büyük
        # olduğu için çalışır); açıkça `None` döndürüp burada ele almak bunu
        # varsayıma bağlı olmaktan çıkarır.
        pencere_baslangic, sayac = now, 0
    else:
        pencere_baslangic, sayac = mevcut
    reset_in_s = window_s - (now - pencere_baslangic)
    if sayac >= limit:
        return BudgetCheck(allowed=False, used=sayac, limit=limit, reset_in_s=reset_in_s)
    sayac += 1
    _yaz(hedef, pencere_baslangic, sayac)
    return BudgetCheck(allowed=True, used=sayac, limit=limit, reset_in_s=reset_in_s)


def _eski_konumu_tasi(
    root: Path, hedef: Path, mevcut: tuple[float, int] | None
) -> tuple[float, int] | None:
    """Proje içindeki eski sayaç dosyasını yeni konuma taşı (yeni kayıt varsa yalnız temizle).

    Eski dosya yeni konum yazıldıktan SONRA silinir; yazılamadıysa yerinde kalır, sayaç kaybolmaz.
    """
    eski = root / LEGACY_BUDGET_PATH
    if not eski.is_file():
        return mevcut
    devralinan = mevcut if mevcut is not None else _oku(eski)
    if mevcut is None and devralinan is not None:
        _yaz(hedef, *devralinan)
    if mevcut is None and devralinan is not None and not hedef.is_file():
        return devralinan
    try:
        eski.unlink()
    except OSError:
        logging.getLogger(__name__).warning("Eski öğretmen bütçe dosyası silinemedi", exc_info=True)
    return devralinan


def _oku(hedef: Path) -> tuple[float, int] | None:
    try:
        veri = json.loads(hedef.read_text(encoding="utf-8"))
        return float(veri["pencere_baslangic"]), int(veri["sayac"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _yaz(hedef: Path, pencere_baslangic: float, sayac: int) -> None:
    """Sayacı geçici dosyaya yazıp `os.replace` ile yerine koy (yarım yazma bozuk JSON bırakmaz).

    Salt-okunur çalışma alanı ya da dolu disk `ask_teacher`'ı bütçe kontrolünde çökertmesin
    (A4-36): yazılamayan sayaç yalnız o pencerede eksik sayılır; bütçe güvenlik sınırı değil,
    ihtiyatlı bir üst sınırdır (bkz. `check_and_spend`).
    """
    gecici = hedef.with_name(f"{hedef.name}.{os.getpid()}.tmp")
    try:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici.write_text(
            json.dumps({"pencere_baslangic": pencere_baslangic, "sayac": sayac}),
            encoding="utf-8",
        )
        gecici.replace(hedef)
    except OSError:
        logging.getLogger(__name__).warning("Öğretmen bütçe sayacı yazılamadı", exc_info=True)
        with contextlib.suppress(OSError):
            gecici.unlink(missing_ok=True)
