"""Geri alınan yazma, tekrar kapısını da serbest bırakır.

Ölçüldü (7 Eylül, 42 görevlik set — `kenar-durumunda-cokme`, `mevcut-projeye-uy`):
adım `replace_range` ile DOĞRU düzeltmeyi yazdı, kabuk çıktısı bile doğruladı
(0.0 ve 7.5). Adım doğrulaması düşünce yazma geri alındı; model aynı doğru
düzenlemeyi yeniden denediğinde `TOOL_CALL_DUPLICATE` ile engellendi. Engelin
gerekçesi "çalışma alanında o zamandan beri ilgili bir değişiklik olmadı" idi —
oysa değişiklik BİZ geri aldığımız için yoktu.

İki kapı birbirini kilitliyordu ve doğru hamle tam da tekrarlanması gereken
hamleydi. Adım hiç ilerleyemedi.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.budget import TurnBudget
from fusion_cli.core.clock import SystemClock


def _butce() -> TurnBudget:
    return TurnBudget(
        clock=SystemClock(),
        max_model_calls=50,
        max_verify_rounds=2,
        max_empty_retries=2,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=99,
    )


def _yazma(butce: TurnBudget, yol: str):
    return butce.signature("replace_range", f'{{"path": "{yol}"}}', mutating=True)


def test_geri_alinan_yazma_tekrar_sayilmaz(tmp_path):
    butce = _butce()
    imza = _yazma(butce, "bol.py")
    butce.count_call(imza)
    assert butce.count_call(imza) == 1, "ikinci çağrı tekrar sayılıyor (kurulum doğru)"

    butce.forget_calls_touching((tmp_path / "bol.py",))

    assert butce.count_call(imza) == 0, "geri alma sonrası aynı düzenleme yine engelli"


def test_geri_alinmayan_dosyanin_tekrari_hala_engelli(tmp_path):
    """Gevşetme DAR olmalı: yalnız geri alınan dosyalar serbest kalır."""
    butce = _butce()
    dokunulmayan = _yazma(butce, "baska.py")
    butce.count_call(dokunulmayan)

    butce.forget_calls_touching((tmp_path / "bol.py",))

    assert butce.count_call(dokunulmayan) == 1


def test_okuma_cagrilari_etkilenmez(tmp_path):
    """Okumanın imzası zaten çağa duyarlıdır; burada bir şey değişmemeli."""
    butce = _butce()
    okuma = butce.signature("read_file", '{"path": "bol.py"}', mutating=False)
    butce.count_call(okuma)

    butce.forget_calls_touching((tmp_path / "bol.py",))

    assert butce.count_call(okuma) == 1


def test_bos_liste_hicbir_seyi_unutturmaz():
    butce = _butce()
    imza = _yazma(butce, "bol.py")
    butce.count_call(imza)

    butce.forget_calls_touching(())

    assert butce.count_call(imza) == 1


def test_gercek_geri_alma_yollari_dosya_adiyla_eslesir(tmp_path: Path):
    """Kayıtta göreli yol, geri almada MUTLAK yol var; eşleşme buna dayanmalı."""
    butce = _butce()
    imza = _yazma(butce, "alt/dizin/kod.py")
    butce.count_call(imza)

    butce.forget_calls_touching((tmp_path / "alt" / "dizin" / "kod.py",))

    assert butce.count_call(imza) == 0
