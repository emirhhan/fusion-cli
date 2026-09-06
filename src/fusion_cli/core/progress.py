"""Bir araç turunun ilerleme puanı.

Karar eskiden İKİLİYDİ: "başarılı araç sayısı ya da dokunulan dosya değişti mi".
Bu, başarısız üç çağrıyla hiç çağrı yapmamayı aynı kefeye koyuyordu ve eşiği
ayarlamak imkânsızdı. SWE-TRACE'in bulgusu, kötü dalı koşarken budamanın sonradan
elemekten iyi olduğu; ama budama kararı ölçülebilir olmalı.

Puan turun KENDİ sinyallerinden hesaplanır — model yorumu değildir — ve saf olduğu
için doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Turun "ilerledi" sayılması için gereken en düşük puan.
#
# 0,5 seçildi çünkü tek bir gerçek değişiklik (mutasyon) tek başına eşiği geçmeli,
# gerçek bir yeni okuma da geçmelidir: keşif turu ilerlemedir. Eşiğin işi, hiçbir
# şey üretmeyen ya da yalnız tekrar/başarısızlık üreten turu ayırmaktır.
PROGRESS_THRESHOLD = 0.5

#: Sinyal ağırlıkları.
#
# BAŞARILI YENİ OKUMA da eşiği geçer: keşif turu ilerlemedir ve bunu yarım saymak,
# "listele → oku → düzelt" akışındaki modeli düzeltmeye varmadan öldürüyordu
# (ölçüldü, kilitlenme ağı "tekrarcı" modeli). Rubriğin değeri okumayı değersiz
# saymakta değil, TEKRARI ve BAŞARISIZLIĞI ayırt etmekte.
_MUTATION_WEIGHT = 0.6
_READ_WEIGHT = 0.5
#: Başarısız ve tekrarlanan çağrılar YALNIZ salt-okuma turunda ceza sayılır.
#
# Ölçüldü (kilitlenme ağı, "tekrarcı" düşman model): ceza değişikliğin üstüne
# binince, gerçekten dosya yazan ama arada bir çağrıyı tekrarlayan tur "ilerleme
# yok" sayılıp kesildi ve iş hiç bitmedi. Değişen dosya yer gerçeğidir: tur
# ilerlemiştir. Döngüye giren model zaten ayrı bir kapıyla (REPEATED_CALL)
# durdurulur; aynı davranışı iki kez cezalandırmak turu öldürüyordu.
_FAILURE_PENALTY = 0.2
_REPEAT_PENALTY = 0.3


@dataclass(frozen=True, slots=True)
class RoundSignals:
    """Bir araç turunda gözlenen sayılar."""

    mutations: int = 0
    new_reads: int = 0
    failures: int = 0
    repeats: int = 0


def score_round(signals: RoundSignals) -> float:
    """Turun ilerleme puanını [0, 1] aralığında hesapla.

    Gerçekleşmiş bir değişiklik ceza ile SİLİNMEZ: dosya değiştiyse tur ilerlemiştir
    ve bunu "ama arada başarısız çağrı da vardı" diye geri almak, çalışan turu
    öldürüyordu (ölçüldü).
    """
    kazanc = signals.mutations * _MUTATION_WEIGHT + signals.new_reads * _READ_WEIGHT
    if signals.mutations:
        return max(0.0, min(1.0, kazanc))
    ceza = signals.failures * _FAILURE_PENALTY + signals.repeats * _REPEAT_PENALTY
    return max(0.0, min(1.0, kazanc - ceza))


def progressed(signals: RoundSignals) -> bool:
    """Tur, budama eşiğini geçti mi?"""
    return score_round(signals) >= PROGRESS_THRESHOLD
