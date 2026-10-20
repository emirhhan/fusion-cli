"""Aynı dosyada ardışık küçük düzenleme serisi uyarısı."""

from __future__ import annotations

from fusion_cli.engines.agent.edit_streak import (
    EDIT_STREAK_THRESHOLD,
    next_streak,
    streak_note,
)


def test_ayni_dosyada_esige_ulasinca_bir_kez_toplu_yol_onerilir():
    seri = ("", 0)
    notlar = []
    for _ in range(EDIT_STREAK_THRESHOLD + 3):
        seri = next_streak(seri, "veri.json")
        notlar.append(streak_note(seri))

    dolu = [n for n in notlar if n]
    assert len(dolu) == 1 and "veri.json" in dolu[0] and "multi_edit" in dolu[0]


def test_baska_dosyaya_gecince_seri_sifirlanir():
    seri = ("", 0)
    for yol in ("a.php", "a.php", "b.php", "a.php", "a.php"):
        seri = next_streak(seri, yol)

    assert seri == ("a.php", 2) and streak_note(seri) is None
