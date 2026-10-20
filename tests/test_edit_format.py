"""Düzenleme sözleşmesi tüm sağlayıcılarda tektir.

Eskiden API yolu satır aralığı (`replace_range`), web yolu search/replace alıyordu ve
şema sağlayıcıya göre daraltılıyordu. Satır aralığı aracı silinen satırı sessizce
kaybettirdi (A2) ve kaldırıldı; artık her sağlayıcı aynı üç aracı görür:
`edit_file` / `multi_edit` (benzersiz tam metin) ve `write_file`.
"""

from __future__ import annotations

from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.tools import build_registry

DUZENLEME_ARACLARI = {"edit_file", "multi_edit", "write_file"}


def _names(policy: ExecutionPolicy) -> set[str]:
    return _permitted(None, build_registry(), policy) or set()


def test_api_ve_web_ayni_duzenleme_araclarini_gorur():
    api = _names(ExecutionPolicy(is_web=False))
    web = _names(ExecutionPolicy(is_web=True))

    assert api >= DUZENLEME_ARACLARI
    assert web >= DUZENLEME_ARACLARI
    assert api == web


def test_satir_araligi_araci_hic_sunulmaz():
    assert "replace_range" not in _names(ExecutionPolicy(is_web=False))
    assert "replace_range" not in _names(ExecutionPolicy(is_web=True))


def test_okuma_araclari_her_saglayicida_acik():
    for policy in (ExecutionPolicy(is_web=False), ExecutionPolicy(is_web=True)):
        assert "read_file" in _names(policy)
