"""Özet, sonraki turun ihtiyaç duyduğu alanları YAPILANDIRILMIŞ verir.

Anthropic'in compaction ölçümü ve blueprint'in Tier 3 kuralı aynı şeyi söylüyor:
özet serbest metin olduğunda "neredeydik" bilgisi eriyor. Dört başlık zorunludur —
hedef, ulaşılan durum, açık işler, kritik kararlar — ve artifact/dosya yolları
özetlenmez, aynen taşınır.
"""

from __future__ import annotations

from pathlib import Path

PROMPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "fusion_cli"
    / "engines"
    / "agent"
    / "prompts"
    / "compress.txt"
).read_text(encoding="utf-8")


def test_ozet_dort_basligi_ister():
    for baslik in ("HEDEF", "DURUM", "AÇIK İŞLER", "KARARLAR"):
        assert baslik in PROMPT


def test_yollar_ve_kanitlar_aynen_tasinir():
    metin = PROMPT.casefold()

    assert "yol" in metin
    assert "aynen" in metin or "birebir" in metin


def test_trace_yer_tutucusu_korunur():
    assert "{trace}" in PROMPT
