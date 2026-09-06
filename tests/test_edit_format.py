"""Düzenleme biçimi modele göre seçilir.

Aider'ın ölçümü: aynı model, farklı düzenleme biçimiyle %20 → %61. Search/replace
blokları satır numarası ve uzunluk tutturmayı gerektirmediği için zayıf modelde
daha sağlam; dört örtüşen düzenleme aracını aynı anda görmek ise seçim hatası
üretir. Bu yüzden modele TEK bir biçim sunulur.
"""

from __future__ import annotations

from fusion_cli.core.model_capability import EditFormat
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.tools import build_registry


def _names(edit_format: EditFormat) -> set[str]:
    policy = ExecutionPolicy(is_web=False, edit_format=edit_format)
    return _permitted(None, build_registry(), policy) or set()


def test_search_replace_biciminde_satir_araligi_sunulmaz():
    names = _names(EditFormat.SEARCH_REPLACE)

    assert "edit_file" in names
    assert "write_file" in names
    assert "replace_range" not in names


def test_satir_araligi_biciminde_tum_duzenleme_araclari_acik():
    names = _names(EditFormat.LINE_RANGE)

    assert {"edit_file", "replace_range", "write_file"} <= names


def test_tam_dosya_biciminde_yalniz_yazma_sunulur():
    names = _names(EditFormat.WHOLE_FILE)

    assert "write_file" in names
    assert "edit_file" not in names
    assert "replace_range" not in names


def test_okuma_araclari_bicimden_etkilenmez():
    for bicim in EditFormat:
        assert "read_file" in _names(bicim)


def test_web_modeli_varsayilan_olarak_search_replace_alir():
    """Web sağlayıcıda araç çağrısı metinden ayrıştırılır; en dayanıklı biçim seçilir."""
    from fusion_cli.config.loader import load_config
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.engines.agent.classify import TaskKind
    from fusion_cli.engines.agent.execution_policy import policy_for

    config = load_config()
    policy = policy_for(
        config,
        ModelSpec(name="ana", model="gemini_web/main/auto"),
        TaskKind.FEATURE,
        "dosyayı düzelt",
    )

    assert policy.edit_format is EditFormat.SEARCH_REPLACE
