"""Ordinary brief static reports do not require magic dependency wording."""

from dataclasses import replace

import pytest

from fusion_cli.engines.agent.teacher_plan import classify_teacher_task

ORDINARY_REPORT = (
    "Python’ın en güncel kararlı sürümünü ve yayımlanma tarihini açıklayan kısa bir "
    "Türkçe HTML raporunu rapor.html olarak hazırla; kaynağı ve erişim tarihini de belirt."
)


@pytest.mark.parametrize(
    "task",
    [
        ORDINARY_REPORT,
        (
            "https://example.org/releases/ sayfasını oku; kısa bir HTML raporunu "
            "sonuc.html olarak hazırla."
        ),
        (
            "Bugünkü hava durumunu kaynağı ve erişim tarihiyle kısa bir HTML raporu "
            "olarak hava.html dosyasına yaz."
        ),
        (
            "Read https://example.net/news/ and create a brief HTML report in "
            "digest.html with source links."
        ),
        (
            "Create a short Turkish HTML report about the latest stable release as "
            "release.html; cite the source and access date."
        ),
        (
            "Read https://example.net/releases.html and https://example.org/history/ "
            "and save a concise report as summary.htm."
        ),
        'Read "https://example.net/news/" and create a brief report as "digest.html".',
        "Source: read https://example.org/news/ and create a brief report as digest.html.",
        "Create a brief Markdown report about the latest stable release as release.md.",
        "Güncel sürümü kaynağından doğrula ve kısa bir metin raporunu sonuc.txt olarak yaz.",
        (
            "Node.js’in güncel kararlı sürümünü açıklayan kısa bir HTML raporunu "
            "rapor.html olarak hazırla."
        ),
        (
            "Node.js güncel kararlı sürümünü araştır; kaynaklarını ve tarihi içeren "
            "kısa raporu rapor.html olarak oluştur."
        ),
        "Create a brief HTML report about Node.js as release.html.",
        "Create a brief report about the latest game release as game-report.html.",
        "HTML formatında kısa bir raporu sonuc.html olarak oluştur.",
        (
            "Fetch the current Node.js release from "
            "https://nodejs.org/en/about/previous-releases "
            "and create a brief HTML report as release.html."
        ),
    ],
)
def test_ordinary_short_static_report_runs_without_automatic_plan(task):
    assert classify_teacher_task(task).size == "basit"


@pytest.mark.parametrize(
    "extra",
    [
        " Kapsamlı sektör analizi ve tüm şirketlerin karşılaştırmasını da ekle.",
        " Ayrıca etkileşimli grafikler ekle.",
        " Add an interactive dashboard.",
        " Add a database and login.",
        " Refresh the source using fetch whenever the page opens.",
        " Add a script loaded from https://example.org/widget.js at runtime.",
        " Ayrıca extra.css oluştur.",
        " Create several output files.",
        " Klasördeki tüm dosyaları sil.",
        " Delete all existing files.",
        " Rename the old directory.",
        " Dosyayı sunucuya gönder.",
        " Send it by email.",
        " Publish it to a server.",
        " Önce öğretmene danış.",
        " Ask the teacher to plan the task first.",
        "\n1. Sunucuyu kur\n2. İstemciyi yaz",
    ],
)
def test_expanded_or_external_report_work_keeps_automatic_plan(extra):
    assert classify_teacher_task(ORDINARY_REPORT + extra).size == "orta-buyuk"


@pytest.mark.parametrize(
    "task",
    [
        "Create report.html containing a comprehensive release analysis.",
        'Create report.html; the example says "create a brief HTML report".',
        "Kısa rapor istemiyorum; rapor.html oluştur.",
        "Kısa olmayan bir HTML raporunu rapor.html olarak oluştur.",
        "Create report.html; not a short report.",
        "Do not create a brief report; create the complete report as report.html.",
        "Create report.html and a brief report in summary.html.",
        "Create a brief interactive report as report.html.",
        "Create a short report as app.py.",
        "Read brief-report.html and fix the rendering bug.",
        "Create a short-circuit analysis report as report.html.",
        "Read file:///etc/passwd; create a brief HTML report as report.html.",
        "Read javascript:alert(1); create a brief HTML report as report.html.",
        'Read "file:///etc/passwd"; create a brief HTML report as report.html.',
        "Read `javascript:alert(1)`; create a brief HTML report as report.html.",
        "Read brief-source.html; create a brief HTML report.",
        "Read source.html and create a brief HTML report.",
        "Read ftp://example.org/news; create a brief HTML report as report.html.",
        "Create report.html, but a brief report is not wanted.",
        "Kısa HTML raporunu rapor.html dosyasından oku ve render hatasını düzelt.",
        "Create a brief HTML report in report.html that updates every minute.",
        "Create a brief HTML report in report.html that fetches fresh data every minute.",
        (
            "Create a brief HTML report report.html covering every technology sector, "
            "economic history, and all geopolitical risks."
        ),
        "Kısa etkileşimli HTML raporunu rapor.html olarak hazırla.",
        "Kısa HTML raporunu rapor.html olarak hazırla; etkileşimli grafikler içersin.",
        "Create a brief HTML report in report.html and implement a Python command-line tool.",
        (
            "Kısa raporu rapor.html olarak oluştur; "
            "ayrıca bir sıralama algoritması geliştir ve test et."
        ),
        "Create a brief HTML report report.html and replace the broken sorting implementation.",
    ],
)
def test_missing_or_rejected_bounded_report_scope_stays_conservative(task):
    assert classify_teacher_task(task).size == "orta-buyuk"


@pytest.mark.parametrize("review_mode", ["ordinary", "off", "manual"])
async def test_ordinary_current_report_preserves_source_artifact_and_review_gates(
    monkeypatch, tmp_path, review_mode
):
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import model_result, tool_call
    from tests.test_teacher_first import _setup

    html = '<main>Source fixture only; not current data. <a href="https://example.org/">Source</a></main>'
    answers = [
        model_result(tool_calls=(tool_call("web_search", query="test release fixture"),)),
        model_result(tool_calls=(tool_call("write_file", path="rapor.html", content=html),)),
        *[model_result("rapor.html hazırlandı; kaynak dosyada.")] * 4,
    ]
    if review_mode == "manual":
        answers.insert(
            0,
            model_result(
                tool_calls=(tool_call("ask_teacher", question="Kaynağı nasıl doğrularım?"),)
            ),
        )
    deps, _sink, teacher, apprentice = _setup(
        monkeypatch,
        tmp_path,
        apprentice_answers=answers,
        teacher_answers=[model_result('{"bulgular": []}')],
    )
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    registry = ToolRegistry()
    reads = []

    def source_fixture(args, context):
        reads.append(args["query"])
        return ToolResult("Fixture only: release A; https://example.org/")

    for tool in build_registry():
        registry.register(replace(tool, run=source_fixture) if tool.name == "web_search" else tool)
    deps.base_registry = registry
    reviews = []

    async def review(*args, **kwargs):
        reviews.append(True)
        return ""

    class FileVerifier:
        calls = 0

        async def verify(self):
            self.calls += 1
            assert (tmp_path / "rapor.html").read_text() == html
            return VerificationResult(ok=True)

    verifier = FileVerifier()
    deps.verifier = verifier
    monkeypatch.setattr(loop.review, "review_turn", review)
    outcome = await loop.run_agent(
        ORDINARY_REPORT, deps, self_review=False if review_mode == "off" else None
    )

    assert outcome.ok and teacher.calls == (0 if review_mode == "ordinary" else 1)
    assert reads == ["test release fixture"]
    assert verifier.calls == 1 and reviews == ([] if review_mode == "off" else [True])
    assert apprentice.calls == (4 if review_mode == "manual" else 3)
    assert any(
        schema["function"]["name"] == "ask_teacher" for schema in apprentice.seen_requests[0]
    )
