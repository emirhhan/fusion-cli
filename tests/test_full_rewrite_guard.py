"""Küçük ve TAMAMI OKUNMUŞ dosyayı toptan yazmak engellenmez.

Kuralın gerekçesi hacimdir: yüz satırlık bir dosyayı baştan üretmek modele yüz
satırlık hata yüzeyi açar. Ölçüldü (6 Eylül, 24 görev × 3 koşu): engellenen 34
toptan yazmanın TAMAMI 1-45 satırlık dosyalardaydı. Tek satırlık bozuk bir
JSON'u onarmanın doğal yolu dosyayı yeniden yazmaktır; kural modeli her
seferinde `replace_range`'e düşürüp tur harcatıyordu.

Kısıt büyük dosyada AYNEN kalır: orada gerekçe hâlâ geçerlidir.
"""

from __future__ import annotations

from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import (
    MAX_LINES_FOR_FULL_REWRITE,
    _State,
    _targeted_edit_required,
)
from tests.test_plan_repair import _deps


def _uyari(tmp_path, *, satir: int, okundu: bool, dusen_duzenleme: int = 0):
    hedef = tmp_path / "kod.py"
    hedef.write_text("x = 1\n" * satir, encoding="utf-8")
    deps = _deps(tmp_path)
    if okundu:
        deps.tool_context.fully_read.add(hedef)
    state = _State()
    state.failed_mutations_in_row = dusen_duzenleme
    return _targeted_edit_required(
        "write_file",
        {"path": "kod.py", "content": "x = 2\n"},
        deps,
        ExecutionPolicy(is_web=True),
        state,
    )


def test_kucuk_ve_okunmus_dosya_toptan_yazilabilir(tmp_path):
    assert _uyari(tmp_path, satir=8, okundu=True) == []


def test_okunmamis_kucuk_dosya_yine_korunur(tmp_path):
    """Gevşetmenin koşulu içeriğin GÖRÜLMÜŞ olmasıdır; boyut tek başına yetmez."""
    assert _uyari(tmp_path, satir=8, okundu=False) != []


def test_buyuk_dosya_okunmus_olsa_da_korunur(tmp_path):
    satir = MAX_LINES_FOR_FULL_REWRITE + 20

    assert _uyari(tmp_path, satir=satir, okundu=True) != []


def test_buyuk_dosyada_hedefli_duzenleme_tikanirsa_cikis_acilir(tmp_path):
    """Eski kaçış yolu korunur: iki başarısız hedefli düzenlemeden sonra serbest."""
    satir = MAX_LINES_FOR_FULL_REWRITE + 20

    assert _uyari(tmp_path, satir=satir, okundu=True, dusen_duzenleme=2) == []
