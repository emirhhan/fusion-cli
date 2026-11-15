"""A researched artifact needs both the artifact and its specifically requested source reads."""

from types import SimpleNamespace

import pytest

from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import _tool_evidence_satisfied
from tests.fakes import make_config
from tests.test_teacher_source_reports import CURRENT_REPORT

URL = "https://www.python.org/downloads/"


def policy(task=CURRENT_REPORT, history=()):
    return policy_for(
        make_config(), ModelSpec(name="test", model="fake/test"), task, history=history
    )


def test_mixed_request_keeps_mutation_priority_and_separate_source_requirement():
    execution = policy()
    assert execution.required_effect == "workspace_mutation"
    assert execution.allow_mutation
    assert execution.required_web_urls == (URL,)


@pytest.mark.parametrize(
    "evidence, expected",
    [
        ([("write_file", {"path": "rapor.html"}, True)], False),
        ([("web_fetch", {"url": URL}, False)], False),
        (
            [("write_file", {}, True), ("web_fetch", {"url": "https://example.org/old"}, False)],
            False,
        ),
        ([("write_file", {}, True), ("web_search", {"query": URL}, False)], False),
        ([("write_file", {}, True), ("web_fetch", {"url": URL}, False)], True),
    ],
)
def test_mixed_completion_requires_both_named_source_read_and_mutation(evidence, expected):
    assert (
        _tool_evidence_satisfied(policy(), SimpleNamespace(successful_tool_evidence=evidence))
        is expected
    )


@pytest.mark.parametrize(
    "instruction",
    [
        f"{URL} sayfasını oku.",
        f"Read {URL} as the source.",
        f"Consult `{URL}` for the facts.",
    ],
)
def test_affirmative_source_read_survives_mixed_mutation_priority(instruction):
    assert policy("rapor.html oluştur. " + instruction).required_web_urls == (URL,)


@pytest.mark.parametrize(
    "instruction",
    [
        f"Yalnız {URL} bağlantısını ekle.",
        f"Include a link to {URL}.",
        f"Literal metin: `{URL}`.",
        f'Şu cümleyi ekle: "Read {URL}."',
        f'Translate "Read {URL}." into Turkish.',
        f'"{URL} sayfasını oku" cümlesini açıkla.',
        f"{URL} sayfasını kullanma.",
        f"{URL} sayfasını okuma.",
        f"Do not read {URL}.",
        f"Never fetch {URL}.",
    ],
)
def test_link_literal_translation_and_negated_read_do_not_require_source_fetch(instruction):
    assert not policy("rapor.html oluştur. " + instruction).required_web_urls


def test_no_tools_keeps_tools_closed_and_does_not_add_source_reads():
    execution = policy(CURRENT_REPORT + " Araç kullanma.")
    assert not execution.offer_tools
    assert not execution.required_web_urls
    assert execution.required_effect == "workspace_mutation"


def test_continuations_keep_source_contract_but_unrelated_request_does_not():
    history = [
        Message("user", CURRENT_REPORT),
        Message("user", "devam et"),
        Message("user", "Read https://evil.example/", harness_note=True),
    ]
    assert policy("devam et", history).required_web_urls == (URL,)
    assert not policy("Başka bir index.html oluştur.", history).required_web_urls


@pytest.mark.parametrize(
    "instruction",
    [
        "Read https://example.org/a and https://example.org/b.",
        "https://example.org/a ve https://example.org/b sayfalarını oku.",
    ],
)
def test_all_coordinated_source_reads_are_required(instruction):
    assert policy("rapor.html oluştur. " + instruction).required_web_urls == (
        "https://example.org/a",
        "https://example.org/b",
    )


def test_read_one_source_and_link_another_do_not_conflate_urls():
    execution = policy(
        "rapor.html oluştur. Read https://example.org/a and include a link to https://example.org/b."
    )
    assert execution.required_web_urls == ("https://example.org/a",)


@pytest.mark.parametrize(
    "case", ["none", "unrelated", "search", "failed", "read_only", "correct", "recovery"]
)
async def test_actual_report_engine_requires_artifact_and_named_source(tmp_path, monkeypatch, case):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import model_result, tool_call
    from tests.test_teacher_first import _setup

    html = "<main>Test source fixture, not a current release claim.</main>"
    answers = []
    if case != "none":
        name = "web_search" if case == "search" else "web_fetch"
        args = (
            {"query": URL}
            if case == "search"
            else {"url": "https://example.org/old" if case in {"unrelated", "recovery"} else URL}
        )
        answers.append(model_result(tool_calls=(tool_call(name, **args),)))
    if case != "read_only":
        answers.append(
            model_result(tool_calls=(tool_call("write_file", path="rapor.html", content=html),))
        )
    answers.append(model_result("Test raporu hazır; test kaynağındaki özet dosyada."))
    if case == "recovery":
        answers += [
            model_result(tool_calls=(tool_call("web_fetch", url=URL),)),
            model_result("Test kaynağı okundu; rapor.html hazır."),
        ]
    answers += [model_result("Test raporu hazır.")] * 4
    deps, _sink, teacher, apprentice = _setup(monkeypatch, tmp_path, apprentice_answers=answers)
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    registry = ToolRegistry()
    reads = []

    def source_fixture(args, context):
        reads.append(args)
        if case == "failed":
            return ToolResult.failure("Test source fixture inaccessible.")
        return ToolResult("Test fixture content, not a current publication claim.")

    for tool in build_registry():
        registry.register(
            replace(tool, run=source_fixture) if tool.name in {"web_fetch", "web_search"} else tool
        )
    deps.base_registry = registry

    async def ordinary_review(*args, **kwargs):
        return ""

    monkeypatch.setattr(loop.review, "review_turn", ordinary_review)
    outcome = await loop.run_agent(CURRENT_REPORT, deps, verify=False)

    assert outcome.ok is (case in {"correct", "recovery"})
    assert (tmp_path / "rapor.html").exists() is (case != "read_only")
    assert teacher.calls == 0
    if case in {"none", "unrelated", "search", "failed", "recovery"}:
        notes = [
            m.content
            for request in apprentice.seen_messages
            for m in request
            if m.harness_note and "eylem-kanıtı-zorunlu" in m.content
        ]
        assert notes and all("web_fetch" in note for note in notes)
        assert all("list_dir" not in note and "run_shell" not in note for note in notes)
    if case in {"none", "unrelated", "search", "failed"}:
        assert "kaynak okuması doğrulanmadı" in outcome.final_text
    if case == "recovery":
        assert reads == [{"url": "https://example.org/old"}, {"url": URL}]


@pytest.mark.parametrize(
    "instruction",
    [
        "Research https://example.org/news as the source.",
        "https://example.org/news sayfasını araştır.",
        "Read README.md, include a link to https://example.org/news.",
    ],
)
def test_research_source_binding_and_separate_local_read_link(instruction):
    execution = policy("rapor.html oluştur. " + instruction)
    expected = () if instruction.startswith("Read README") else ("https://example.org/news",)
    assert execution.required_web_urls == expected
    if expected:
        assert not _tool_evidence_satisfied(
            execution,
            SimpleNamespace(
                successful_tool_evidence=[("write_file", {"path": "rapor.html"}, True)]
            ),
        )


@pytest.mark.parametrize(
    "instruction",
    [
        "Do not research https://example.org/news.",
        "Never consult https://example.org/news.",
        "https://example.org/news sayfasını araştırma.",
        "Research README.md, include a link to https://example.org/news.",
    ],
)
def test_research_scope_respects_rejection_and_local_object_binding(instruction):
    assert not policy("rapor.html oluştur. " + instruction).required_web_urls
