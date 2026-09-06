"""Düzenleme biçimi ŞEMAYI daraltır, YETENEĞİ kapatmaz.

Ölçüldü (6 Eylül canlı koşusu): web yolunda `search_replace` biçimi seçilince
`replace_range` şemadan çıkarıldı — buraya kadar doğru, amaç seçim kalabalığını
azaltmak. Ama araç dispatcher'da da kapandı ve model onu yine çağırdığında
"araç bu adımın izin verilen kapsamında değil" cevabını aldı; `bozuk-json-veriyi-onar`,
`mevcut-projeye-uy` ve `regresyon-testi-yaz` görevleri bu yüzden düştü.

Ayrım nettir: şemadan çıkarmak "bunu ÖNERMİYORUM" demektir, engellemek "bunu
YAPAMAZSIN". İkincisi yalnız adım kapsamı ve mutasyon izni için geçerlidir.
"""

from __future__ import annotations

from fusion_cli.core.model_capability import EditFormat
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.tools import build_registry


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(is_web=True, edit_format=EditFormat.SEARCH_REPLACE)


def test_semada_onerilmeyen_bicim_gizlenir():
    sema = _permitted(None, build_registry(), _policy(), for_schema=True) or set()

    assert "replace_range" not in sema
    assert "edit_file" in sema


def test_dispatcher_gizlenen_araci_engellemez():
    calistirilabilir = _permitted(None, build_registry(), _policy()) or set()

    assert "replace_range" in calistirilabilir


def test_adim_kapsami_hala_engeller():
    """Gerçek kapsam kısıtı korunur: gevşetme yalnız BİÇİM tercihine aittir."""
    policy = ExecutionPolicy(
        is_web=True,
        edit_format=EditFormat.SEARCH_REPLACE,
        allowed_tool_names=frozenset({"read_file"}),
    )

    calistirilabilir = _permitted(None, build_registry(), policy) or set()

    assert "replace_range" not in calistirilabilir
    assert "read_file" in calistirilabilir


def test_mutasyon_kapaliyken_yazma_araclari_yine_kapali():
    policy = ExecutionPolicy(is_web=True, allow_mutation=False)

    calistirilabilir = _permitted(None, build_registry(), policy) or set()

    assert "write_file" not in calistirilabilir
