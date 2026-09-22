"""Öğretmen çağrı bütçesi — saatlik, `.fusion/` altında (Faz 4, Görev 4).

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
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Kova ile AYNI mantıkta ama çok daha kaba bir üst sınır — bkz. modül docstring'i.
HOURLY_LIMIT = 60
WINDOW_S = 3600.0
BUDGET_PATH = ".fusion/ogretmen-butce.json"


@dataclass(frozen=True, slots=True)
class BudgetCheck:
    """Bir bütçe kontrolünün sonucu."""

    allowed: bool
    #: Bu pencerede harcanan (kontrol İZİN VERDİYSE +1 dahil) çağrı sayısı.
    used: int
    limit: int
    #: Pencerenin sıfırlanmasına kalan saniye.
    reset_in_s: float


def check_and_spend(
    root: Path, *, now: float, limit: int = HOURLY_LIMIT, window_s: float = WINDOW_S
) -> BudgetCheck:
    """Bu saatlik pencerede hak var mı kontrol et; VARSA harca (dosyaya yaz).

    Dosya bozuksa ya da okunamıyorsa sıfırdan başlanır — bütçe dosyası bir
    GÜVENLİK sınırı değildir, en kötü ihtimalle bir pencere fazladan sıfırlanır.
    """
    hedef = root / BUDGET_PATH
    mevcut = _oku(hedef)
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


def _oku(hedef: Path) -> tuple[float, int] | None:
    try:
        veri = json.loads(hedef.read_text(encoding="utf-8"))
        return float(veri["pencere_baslangic"]), int(veri["sayac"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _yaz(hedef: Path, pencere_baslangic: float, sayac: int) -> None:
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        json.dumps({"pencere_baslangic": pencere_baslangic, "sayac": sayac}), encoding="utf-8"
    )
