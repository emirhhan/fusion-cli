"""Reading sources does not turn a standalone report into a runtime integration."""

import pytest

from fusion_cli.engines.agent.teacher_plan import classify_teacher_task, is_bounded_single_file_task
from tests.test_mixed_current_research import assert_research_and_artifact_required

CURRENT_REPORT = (
    "Bu klasörde rapor.html oluştur: Python’ın bugün resmi indirme sayfasında listelenen en güncel "
    "iki kararlı sürümünü ve yayımlanma tarihlerini resmi kaynaktan doğrula. "
    "https://www.python.org/downloads/ sayfasını oku. Türkçe kısa raporda kaynak bağlantısı ve "
    "bugünkü erişim tarihini belirt; ön sürümleri kararlı sürüm diye yazma. "
    "Tek bir HTML dosyası olsun; harici bağımlılık kullanma."
)


@pytest.mark.parametrize("verb", ["okuyarak", "okuyup"])
def test_reading_converb_binds_official_source_without_teacher(verb):
    from fusion_cli.engines.effects.detect import requested_web_urls

    task = f"https://example.org/releases/ sayfasını {verb} kısa raporu rapor.html olarak hazırla."
    assert requested_web_urls(task, source_reads_only=True) == ("https://example.org/releases/",)
    assert is_bounded_single_file_task(task)


@pytest.mark.parametrize(
    "task",
    [
        "https://example.org/releases/ sayfasını okumayarak kısa raporu rapor.html olarak hazırla.",
        'Örnekte "https://example.org/releases/ sayfasını okuyarak" yazıyor; rapor.html oluştur.',
        "https://example.org/releases/ sayfasını okuma; kısa raporu rapor.html olarak hazırla.",
    ],
)
def test_reading_converb_never_admits_negative_or_quoted_source(task):
    from fusion_cli.engines.effects.detect import requested_web_urls

    assert requested_web_urls(task, source_reads_only=True) == ()


@pytest.mark.parametrize(
    "task",
    [
        CURRENT_REPORT,
        "Tek HTML dosyası olarak rapor.html oluştur. Harici bağımlılık kullanma. "
        "https://example.org/releases.html sayfasını oku ve sürüm tarihlerini "
        "kaynaklarıyla özetle.",
        "Create a single HTML file report.html with no external dependencies. "
        "Read https://example.org/releases.html and https://example.net/history.html as sources. "
        "Summarize the latest two stable releases with published dates and source access dates.",
        "Read the official source https://example.org/news/ and create a single HTML file "
        "report.html. Use no external dependencies. Include source links and today's access date.",
    ],
)
def test_source_reading_report_is_bounded_without_preflight_teacher(task):
    assert is_bounded_single_file_task(task)
    assert classify_teacher_task(task).size == "basit"
    assert_research_and_artifact_required(task)


@pytest.mark.parametrize(
    "extra",
    [
        " Ayrıca https://api.example.org/data API üzerinden canlı verileri getir.",
        " Stil dosyasını CDN https://example.org/style.css üzerinden yükle.",
        " Include a script from https://example.org/client.js at runtime.",
        " Fetch https://example.org/data whenever the page opens.",
        " https://example.org/data adresinden her açılışta verileri çek.",
        " https://example.org/data kullan.",
        " Add authentication and login.",
        " Kullanıcı kimlik doğrulaması ve veritabanı ekle.",
        " Deploy the report to a server.",
        " Siteyi yayına al.",
        " Raporu yayımla.",
        " Rapor yayınlansın.",
        " Publish the report.",
        " Ayrıca style.css dosyasını oluştur.",
        " Create two files, report.html and main.js.",
        " Önce öğretmene danış.",
    ],
)
def test_runtime_dependency_or_expanded_source_report_keeps_teacher(extra):
    task = CURRENT_REPORT + extra
    assert not is_bounded_single_file_task(task)
    assert classify_teacher_task(task).size == "orta-buyuk"


@pytest.mark.parametrize(
    "scope",
    [
        'Örnekte "Tek HTML dosyası olsun; harici bağımlılık kullanma" yazıyor.',
        '"Tek HTML dosyası olsun" örneğini incele. Harici bağımlılık kullanma.',
        'Tek HTML dosyası olsun. "Harici bağımlılık kullanma" örneğini açıkla.',
        "Tek HTML dosyası olsun istemiyorum. Harici bağımlılık kullanma.",
        "Tek HTML dosyası olsun. Harici bağımlılık kullanma demiyorum.",
    ],
)
def test_quoted_or_negated_self_containment_does_not_authorize_bounded_route(scope):
    task = "rapor.html oluştur. https://example.org/releases/ sayfasını oku. " + scope
    assert not is_bounded_single_file_task(task)
    assert classify_teacher_task(task).size == "orta-buyuk"


async def test_report_engine_reads_sources_without_forced_teacher_and_keeps_review(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import model_result, tool_call
    from tests.test_teacher_first import _setup

    # Deliberately a test fixture, not a claim about current Python releases.
    html = '<main>Test source fixture: stable A and B. <a href="https://www.python.org/downloads/">Source</a></main>'
    answers = [
        model_result(tool_calls=(tool_call("web_fetch", url="https://www.python.org/downloads/"),))
    ]
    answers.extend(
        [
            model_result(tool_calls=(tool_call("write_file", path="rapor.html", content=html),)),
            *[model_result("rapor.html oluşturuldu; test kaynağının özeti dosyada.")] * 4,
        ]
    )
    deps, _sink, teacher, apprentice = _setup(monkeypatch, tmp_path, apprentice_answers=answers)
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    registry = ToolRegistry()
    reads = []

    def source_fixture(args, context):
        reads.append(args["url"])
        return ToolResult("Test source fixture only: stable A and B; not current publication data.")

    for tool in build_registry():
        registry.register(replace(tool, run=source_fixture) if tool.name == "web_fetch" else tool)
    deps.base_registry = registry
    reviews = []

    async def ordinary_review(*args, **kwargs):
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
    monkeypatch.setattr(loop.review, "review_turn", ordinary_review)
    outcome = await loop.run_agent(CURRENT_REPORT, deps)

    assert (tmp_path / "rapor.html").read_text() == html
    assert teacher.calls == 0
    assert outcome.ok
    assert reads == ["https://www.python.org/downloads/"]
    assert verifier.calls == 1 and reviews == [True]
    assert apprentice.calls == 3
    assert any(
        schema["function"]["name"] == "ask_teacher" for schema in apprentice.seen_requests[0]
    )


@pytest.mark.parametrize(
    "instruction",
    [
        "Research https://example.org/news as the source.",
        "https://example.org/news sayfasını araştır.",
    ],
)
def test_teacher_and_completion_share_source_research_semantics(instruction):
    task = "Tek HTML dosyası olarak rapor.html oluştur. Harici bağımlılık kullanma. " + instruction
    assert is_bounded_single_file_task(task)
    from fusion_cli.engines.effects.detect import requested_web_urls

    assert requested_web_urls(task, source_reads_only=True) == ("https://example.org/news",)
