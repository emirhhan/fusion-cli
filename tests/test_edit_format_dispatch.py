"""Araç engellemesi yalnız adım kapsamı ve mutasyon izni içindir.

Ölçüldü (6 Eylül canlı koşusu): bir düzenleme aracı dispatcher'da da kapatılınca
model onu yine çağırdı, "araç bu adımın izin verilen kapsamında değil" cevabını
aldı ve üç görev bu yüzden düştü. Düzenleme sözleşmesi artık tüm sağlayıcılarda
tek olduğundan biçime göre gizleme de kalktı; engelleme yalnız gerçek kısıtlardan
(adım kapsamı, mutasyon izni) gelir.
"""

from __future__ import annotations

from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.tools import build_registry


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(is_web=True)


def test_sema_ve_dispatcher_ayni_duzenleme_araclarini_acar():
    calistirilabilir = _permitted(None, build_registry(), _policy()) or set()

    assert {"edit_file", "multi_edit", "write_file"} <= calistirilabilir


def test_adim_kapsami_hala_engeller():
    """Gerçek kapsam kısıtı korunur."""
    policy = ExecutionPolicy(
        is_web=True,
        allowed_tool_names=frozenset({"read_file"}),
    )

    calistirilabilir = _permitted(None, build_registry(), policy) or set()

    assert "edit_file" not in calistirilabilir
    assert "read_file" in calistirilabilir


def test_mutasyon_kapaliyken_yazma_araclari_yine_kapali():
    policy = ExecutionPolicy(is_web=True, allow_mutation=False)

    calistirilabilir = _permitted(None, build_registry(), policy) or set()

    assert "write_file" not in calistirilabilir


def test_bos_arac_kumesi_planlamaya_yonetim_araci_sizdirmaz():
    assert _permitted(set(), build_registry(), _policy()) == set()
