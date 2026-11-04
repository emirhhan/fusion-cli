"""Çıktı sözleşmesi yazım noktalamasından bağımsız ve gerçek dosyaya bağlıdır."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.output_verify import OutputPathVerifier, requested_outputs_in


@pytest.mark.parametrize(
    "task", ["Raporu report.pdf olarak kaydet", "Raporu `report.pdf` olarak kaydet"]
)
def test_plain_output_filename_has_same_contract_as_markdown(task):
    assert requested_outputs_in(task) == ("report.pdf",)


def test_output_contract_never_accepts_external_paths():
    assert requested_outputs_in("Save /tmp/report.pdf") == ()
    assert requested_outputs_in("Save ../report.pdf") == ()
    assert requested_outputs_in("Save https://evil.test/report.pdf") == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["missing", "directory", "empty", "bad_json", "bad_png", "bad_pdf"]
)
async def test_requested_artifact_requires_real_readable_nonempty_file(tmp_path, kind):
    names = {"bad_json": "report.json", "bad_png": "report.png", "bad_pdf": "report.pdf"}
    name = names.get(kind, "report.txt")
    output = tmp_path / name
    if kind == "directory":
        output.mkdir()
    elif kind != "missing":
        output.write_bytes(b"" if kind == "empty" else b"not a valid format")
    context = ToolContext(root=tmp_path)
    context.requested_outputs.add(name)
    context.touched.add(output)
    result = await OutputPathVerifier(context).verify()
    assert not result.ok, kind


@pytest.mark.asyncio
async def test_missing_requested_output_is_checked_even_without_other_writes(tmp_path):
    context = ToolContext(root=tmp_path)
    context.requested_outputs.add("report.txt")
    assert not (await OutputPathVerifier(context).verify()).ok


@pytest.mark.asyncio
async def test_existing_unchanged_file_does_not_satisfy_new_delivery(tmp_path):
    from fusion_cli.engines.agent.output_verify import capture_output_baselines

    target = tmp_path / "report.txt"
    target.write_text("eski rapor")
    context = ToolContext(root=tmp_path)
    context.requested_outputs.add("report.txt")
    capture_output_baselines(context)
    context.touched.add(tmp_path / "unrelated.py")
    assert not (await OutputPathVerifier(context).verify()).ok
    target.write_text("bu turun yeni raporu")
    assert (await OutputPathVerifier(context).verify()).ok


@pytest.mark.parametrize(
    "task",
    [
        "Raporu `Kasım Raporu.pdf` olarak kaydet",
        'Raporu "Kasım Raporu.pdf" olarak kaydet',
    ],
)
def test_quoted_output_with_spaces_is_one_complete_filename(task):
    assert requested_outputs_in(task) == ("Kasım Raporu.pdf",)


def test_absolute_output_is_accepted_only_inside_explicit_workspace(tmp_path):
    path = tmp_path / "Kasım Raporu.pdf"
    assert requested_outputs_in(f'Save "{path}"', root=tmp_path) == ("Kasım Raporu.pdf",)
    assert requested_outputs_in('Save "/tmp/outside.pdf"', root=tmp_path) == ()


@pytest.mark.asyncio
async def test_agent_verify_does_not_skip_explicit_output_without_mutation(tmp_path):
    from types import SimpleNamespace

    from fusion_cli.engines.agent.loop import _verify

    context = ToolContext(root=tmp_path)
    context.requested_outputs.add("report.txt")
    deps = SimpleNamespace(tool_context=context, verifier=OutputPathVerifier(context))
    result = await _verify(
        SimpleNamespace(mutating_tool_calls_made=0), deps, plan_mode=False, depth=0
    )
    assert result is not None and not result.ok


def test_large_artifact_is_unverified_without_unbounded_parser_read(tmp_path):
    from fusion_cli.engines.agent.artifact_verify import inspect_artifact

    target = tmp_path / "large.json"
    target.write_bytes(b"[" + b"0," * 4_500_000 + b"0]")
    result = inspect_artifact(target)
    assert not result.problem
    assert result.warning


def test_compressed_office_member_size_is_bounded(tmp_path):
    import zipfile

    from fusion_cli.engines.agent.artifact_verify import inspect_artifact

    target = tmp_path / "large.docx"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", "<root>" + "x" * 9_000_000 + "</root>")
    result = inspect_artifact(target)
    assert not result.problem
    assert result.warning
