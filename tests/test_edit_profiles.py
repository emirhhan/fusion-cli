"""Düzenleme tercihi yetkiyi değiştirmeden gerçek yüzeye ulaşır."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.tools import build_registry
from tests.fakes import make_config


@pytest.mark.parametrize("preference,tool_name", [("exact", "edit_file"), ("whole", "write_file")])
def test_tercih_native_aciklamaya_tasinir(preference: str, tool_name: str) -> None:
    registry = build_registry()
    original = registry.schemas()
    selected = registry.schemas(edit_format=preference)
    assert [item["function"]["name"] for item in selected] == [
        item["function"]["name"] for item in original
    ]
    tool = next(item["function"] for item in selected if item["function"]["name"] == tool_name)
    assert "Bu turun önerilen düzenleme biçimi" in tool["description"]
    assert registry.schemas() == original


def test_salt_okunur_yuzey_tercihle_genislemez() -> None:
    schemas = build_registry().schemas({"read_file"}, edit_format="whole")
    assert [item["function"]["name"] for item in schemas] == ["read_file"]
    assert "önerilen düzenleme" not in str(schemas)


def test_politika_model_tercihini_dondurur(tmp_path) -> None:
    config = make_config(memory_dir=tmp_path)
    spec = replace(config.agent, recommended_edit_format="exact")
    policy = policy_for(config, spec, "dosyayı düzelt")
    assert policy.edit_format == "exact"
    assert replace(spec, recommended_edit_format="whole").recommended_edit_format == "whole"
    assert policy.edit_format == "exact"


def test_varsayilan_tercih_yok() -> None:
    assert ModelSpec("agent", "yerel/test").recommended_edit_format is None
    assert build_registry().schemas() == build_registry().schemas(edit_format=None)


async def test_gercek_model_cagrisi_frozen_tercihi_istege_ve_semaya_verir(
    tmp_path, monkeypatch
) -> None:
    from evals.agent_runner import _EvalApproval, _NullPublisher

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.core.types import Message, ModelResult
    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider

    config = make_config(memory_dir=tmp_path)
    spec = replace(config.agent, recommended_edit_format="whole")
    config = replace(config, agent=spec)
    requests = []

    class CapturingProvider(ScriptedProvider):
        def _next(self, request):
            requests.append(request)
            return super()._next(request)

    provider = CapturingProvider([ModelResult("agent", spec.model, "tamam", 1, True)])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = loop.AgentDeps(config, _NullPublisher(), _EvalApproval(), ToolContext(root=tmp_path))
    execution = policy_for(config, spec, "dosyayı düzelt")
    result = await loop._call_model(
        [Message("user", "düzelt")],
        deps,
        deps.base_registry,
        state=loop._State(),
        execution=execution,
    )
    assert result.ok
    request = requests[0]
    assert request.edit_format == "whole"
    assert any("Bu turun önerilen düzenleme biçimi" in str(schema) for schema in request.tools)


@pytest.mark.parametrize("preference", ["exact", "whole"])
def test_uyari_reddetme_olarak_sunulmaz(tmp_path, monkeypatch, preference) -> None:
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import files

    target = tmp_path / "dosya.js"
    target.write_text("const adet = 1;\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    files.read_file({"path": "dosya.js"}, context)
    monkeypatch.setattr(files, "syntax_note", lambda path, context: "\nUYARI: sözdizimi hatası")
    if preference == "exact":
        result = files.edit_file({"path": "dosya.js", "old": "1", "new": "2"}, context)
    else:
        result = files.write_file({"path": "dosya.js", "content": "const adet = 2;\n"}, context)
    assert result.ok
    assert "UYARI" in result.output
    assert target.read_text(encoding="utf-8") == "const adet = 2;\n"


def test_efektif_kayit_edit_tercihini_ve_fallback_kapisini_kapsar(tmp_path) -> None:
    from evals.effective_config import project_effective

    config = make_config(memory_dir=tmp_path)
    original = project_effective(config, config.agent, "eval")
    selected = replace(config.agent, recommended_edit_format="whole")
    updated = project_effective(replace(config, agent=selected), selected, "eval")
    assert original.digest != updated.digest
    fields = {field.path: field for field in updated.fields}
    assert "runtime.auto_web_fallback" in fields
    assert any(name.endswith("recommended_edit_format") for name in fields)
