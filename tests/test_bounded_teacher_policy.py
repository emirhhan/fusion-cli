"""Bounded direct execution preserves real verification and optional consultation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.events import SelfReviewFinished, SelfReviewStarted
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop, teacher_flow
from fusion_cli.engines.agent.teacher_plan import (
    classify_teacher_task,
    is_bounded_single_file_task,
)
from tests.fakes import model_result, tool_call
from tests.test_teacher_first import _setup

COUNTER_TASK = (
    "Bu klasörde index.html oluştur: Türkçe bir sayaç sayfası olsun. İlk değer 0; "
    "Artır düğmesine her basışta sayı bir artsın, Sıfırla düğmesi 0 yapsın. "
    "Tek HTML dosyası olsun, harici bağımlılık kullanma. Çalıştığını kontrol et "
    "ve dosya yolunu ver."
)

FUNCTION_FIX_TASK = (
    "invoice.py içindeki invoice_total fonksiyonunda vergi yüzdesi yanlış uygulanıyor. "
    "Fonksiyon imzasını ve miktar varsayılanını koruyarak hatayı düzelt; "
    "vergi argümanı yüzde anlamına gelsin. Mevcut testleri değiştirme, bağımlılık kurma. "
    "Test komutu: /tmp/project/.venv/bin/python -m pytest -q."
)

DEMO_SITE_TASK = (
    "Tek bir index.html dosyasında Türkçe, mobil uyumlu küçük bir danışmanlık sitesi oluştur. "
    "Başlık, üç hizmet kartı ve ad/e-posta/mesaj alanlı bir iletişim formu olsun. "
    "Form yalnız yerel bir demo: hiçbir yere veri göndermesin. "
    "Harici font, resim, CDN veya bağımlılık kullanma."
)


@pytest.mark.parametrize("task", [FUNCTION_FIX_TASK, DEMO_SITE_TASK])
def test_named_local_function_fix_and_explicit_dependency_free_demo_skip_preflight(task):
    assert classify_teacher_task(task).size == "basit"


@pytest.mark.parametrize(
    "suffix",
    [
        " Ayrıca ödeme API entegrasyonu yap.",
        " API ekle, CDN kullanma.",
        " CDN ekle, harici bağımlılık kullanma.",
        " İkinci olarak auth.py dosyasını değiştir.",
        " Öğretmene danış.",
        " Veritabanına bağla.",
        " Uygulamayı deploy et.",
    ],
)
@pytest.mark.parametrize("task", [FUNCTION_FIX_TASK, DEMO_SITE_TASK])
def test_bounded_local_work_does_not_hide_a_separate_expanded_request(task, suffix):
    assert classify_teacher_task(task + suffix).size == "orta-buyuk"


@pytest.mark.parametrize(
    "task",
    [
        "invoice.py içindeki hatayı düzelt; bağımlılık kurma.",
        "invoice.py içindeki invoice_total fonksiyonundaki hatayı düzelt.",
        FUNCTION_FIX_TASK.replace("bağımlılık kurma", "bağımlılık kurma demiyorum"),
        FUNCTION_FIX_TASK.replace("koruyarak", "korumadan"),
        "Fix function invoice_total in invoice.py. Do not preserve the signature. "
        "Do not install dependencies.",
        DEMO_SITE_TASK.replace("kullanma.", "kullanma demiyorum."),
    ],
)
def test_underspecified_or_rejected_constraints_keep_normal_planning(task):
    assert classify_teacher_task(task).size == "orta-buyuk"


@pytest.mark.parametrize(
    "task",
    [
        COUNTER_TASK,
        "Tek Python dosyası olarak calc.py oluştur. Sadece standart kütüphane kullan; "
        "girilen sayıları topla ve sonucu yazdır.",
        "Create a single HTML file index.html for a local timer. "
        "Use no external dependencies. Verify it works.",
    ],
)
def test_explicit_self_contained_single_file_does_not_force_teacher_plan(task):
    assert classify_teacher_task(task).size == "basit"


@pytest.mark.parametrize(
    "scope",
    [
        "Tek HTML dosyası olmasın.",
        "Tek bir dosya yazma.",
        "Tek dosya değil, modüler bir proje olsun.",
    ],
)
def test_negated_single_file_scope_is_not_an_affirmative_bounded_request(scope):
    task = "index.html oluştur. Harici bağımlılık kullanma. " + scope
    assert not is_bounded_single_file_task(task)
    assert classify_teacher_task(task).size == "orta-buyuk"


@pytest.mark.parametrize(
    "publication", ["Siteyi yayına al.", "Sayfayı yayınla.", "Projeyi yayımla."]
)
def test_turkish_publication_keeps_external_work_on_teacher_route(publication):
    task = COUNTER_TASK + " " + publication
    assert not is_bounded_single_file_task(task)
    assert classify_teacher_task(task).size == "orta-buyuk"


@pytest.mark.parametrize(
    "suffix",
    [
        " Ayrıca style.css dosyasını oluştur.",
        " Verileri dış API üzerinden getir.",
        " Önce öğretmene danış ve onun planını uygula.",
        " Ask the teacher to review the implementation.",
        " Bir veritabanına bağlan ve kullanıcı hesaplarını sakla.",
        " Dosyayı sunucuya deploy et.",
        "\n1. Sunucuyu kur\n2. İstemciyi yaz",
        " Ayrıntılar: " + "ek gereksinim " * 100,
    ],
)
def test_dependency_or_expanded_scope_keeps_teacher_workflow(suffix):
    assert classify_teacher_task(COUNTER_TASK + suffix).size == "orta-buyuk"


@pytest.mark.parametrize(
    "task",
    [
        "index.html dosyasını oluştur ve çalıştığını kontrol et.",
        "Tek HTML dosyası olarak index.html oluştur ve çalıştığını kontrol et.",
        "index.html ve main.js oluştur. Harici bağımlılık kullanma.",
        "src/app.py dosyasındaki hatayı düzelt.",
    ],
)
def test_unspecified_self_containment_or_multiple_files_are_not_optimized(task):
    assert classify_teacher_task(task).size == "orta-buyuk"


class _FileVerifier:
    def __init__(self, root, *, ok=True):
        self.root = root
        self.ok = ok
        self.calls = 0

    async def verify(self):
        self.calls += 1
        assert (self.root / "index.html").read_text() == "<main>Sayaç</main>"
        return VerificationResult(
            ok=self.ok,
            findings=() if self.ok else ("Synthetic blocking verification finding",),
        )


def _writer_answers(*prefix):
    return [
        *prefix,
        model_result(
            tool_calls=(tool_call("write_file", path="index.html", content="<main>Sayaç</main>"),)
        ),
        model_result("index.html oluşturuldu; doğrulama durumu aşağıdadır."),
    ]


async def test_bounded_task_runs_directly_but_keeps_ordinary_review_and_verifier(
    monkeypatch, tmp_path
):
    deps, sink, teacher, apprentice = _setup(
        monkeypatch, tmp_path, apprentice_answers=_writer_answers()
    )
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    verifier = _FileVerifier(tmp_path)
    deps.verifier = verifier
    reviewed = []

    async def ordinary_review(*args, **kwargs):
        reviewed.append(kwargs)
        return ""

    monkeypatch.setattr(loop.review, "review_turn", ordinary_review)
    result = await loop.run_agent(COUNTER_TASK, deps)

    assert result.ok
    assert teacher.calls == 0
    assert apprentice.calls == 2
    assert verifier.calls == 1 and len(reviewed) == 1
    assert any(isinstance(e, SelfReviewStarted) for e in sink.events)
    assert any(isinstance(e, SelfReviewFinished) and e.completed for e in sink.events)
    assert not deps.tool_context.todos.has_pending
    assert any(
        schema["function"]["name"] == "ask_teacher" for schema in apprentice.seen_requests[0]
    )


async def test_ordinary_review_disable_retains_teacher_review(monkeypatch, tmp_path):
    deps, _sink, teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[model_result('{"bulgular": []}')],
        apprentice_answers=_writer_answers(),
    )
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    deps.verifier = _FileVerifier(tmp_path)
    result = await loop.run_agent(COUNTER_TASK, deps, self_review=False)

    assert result.ok and teacher.calls == 1
    assert "bulgular" in teacher.seen_messages[0][0].content


async def test_bounded_task_can_voluntarily_consult_teacher(monkeypatch, tmp_path):
    deps, _sink, teacher, apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[model_result("Olay dinleyicilerini düğmelere bağla.")],
        apprentice_answers=_writer_answers(
            model_result(
                tool_calls=(tool_call("ask_teacher", question="Düğmeleri nasıl bağlayayım?"),)
            )
        ),
    )
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    deps.verifier = _FileVerifier(tmp_path)

    async def ordinary_review(*args, **kwargs):
        return ""

    monkeypatch.setattr(loop.review, "review_turn", ordinary_review)
    result = await loop.run_agent(COUNTER_TASK, deps)

    assert result.ok and teacher.calls == 1 and apprentice.calls == 3


@pytest.mark.parametrize("ordinary_review_enabled", [False, True])
async def test_actual_multiple_file_changes_retain_teacher_review(
    monkeypatch, tmp_path, ordinary_review_enabled
):
    deps, _sink, _teacher, _apprentice = _setup(
        monkeypatch, tmp_path, teacher_answers=[model_result('{"bulgular": []}')]
    )
    for name in ("index.html", "extra.js"):
        path = tmp_path / name
        deps.tool_context.changes.record(path)
        path.write_text("generated")
    from fusion_cli.tools.builtin import build_registry

    registry = build_registry()
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_: True)
    asked = []

    async def review_question(*args, **kwargs):
        asked.append(kwargs)
        return '{"bulgular": []}'

    monkeypatch.setattr(teacher_flow, "_ask", review_question)
    findings = await teacher_flow.review_teacher_changes(
        COUNTER_TASK,
        loop.AgentOutcome("Dosyalar oluşturuldu", [], mutating_tool_calls_made=2),
        deps,
        registry,
        ordinary_self_review_enabled=ordinary_review_enabled,
    )

    assert findings == () and len(asked) == 1


async def test_blocking_verifier_failure_is_not_hidden_by_review_dedup(monkeypatch, tmp_path):
    deps, _sink, _teacher, _apprentice = _setup(
        monkeypatch, tmp_path, apprentice_answers=_writer_answers()
    )
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))
    verifier = _FileVerifier(tmp_path, ok=False)
    deps.verifier = verifier

    async def no_repair(_finding, outcome, _deps):
        return outcome

    async def ordinary_review(*args, **kwargs):
        return ""

    monkeypatch.setattr(loop, "_fix_findings", no_repair)
    monkeypatch.setattr(loop.review, "review_turn", ordinary_review)
    result = await loop.run_agent(COUNTER_TASK, deps)

    assert not result.ok
    assert verifier.calls >= 1
    assert "Synthetic blocking verification finding" in result.final_text
