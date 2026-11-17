"""Bellek kaynak etiketi (yol haritası 5c): dış içerik okunan turdan çıkan ders düşük güvenle
"dış kaynaklı" kaydedilir; dış içeriksiz başarılı turda doğrulanmadan güven kazanmaz."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.events import LessonsLearned
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.lesson_runtime import LessonRuntimeContext
from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import learning, learning_steps
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.memory.lesson_scoring import LESSON_CONFIDENCE_FLOOR, reinforced
from fusion_cli.memory.lessons import as_prompt_block

from .fakes import make_config


def _ders(metin: str = "pip yerine uv kullan", **alan) -> Lesson:
    return Lesson(text=metin, kind=LessonKind.SUCCESS, **alan)


# --- dış içerik tespiti ------------------------------------------------------


@pytest.mark.parametrize(
    "ad",
    ["web_fetch", "web_search", "read_url_content", "browser_read", "chrome_page",
     "godot__run_scene", "clone_site", "site_crawl"],
)  # fmt: skip
def test_dis_icerik_araclari_taninir(ad: str) -> None:
    assert learning.reads_external_content((ToolUse(ad),))


@pytest.mark.parametrize(
    "ad", ["read_file", "edit_file", "run_shell", "start_preview", "recall_lessons", "git"]
)
def test_yerel_araclar_dis_kaynak_degildir(ad: str) -> None:
    assert not learning.reads_external_content((ToolUse(ad),))


def test_basarisiz_dis_cagri_dis_icerik_getirmedi() -> None:
    assert not learning.reads_external_content((ToolUse("web_fetch", ok=False),))


def test_mark_external_guveni_dusurur_ve_etiketler() -> None:
    sonuc = learning.mark_external((_ders(), _ders("x", confidence=0.2)), 0.5)

    assert [d.external for d in sonuc] == [True, True]
    assert [d.confidence for d in sonuc] == [0.5, 0.2]  # zaten düşükse korunur


# --- güven mekanizması (saf) ---------------------------------------------------


def test_dis_kaynakli_ders_dis_icerikli_basariyla_guven_kazanmaz() -> None:
    ders = _ders(confidence=0.5, external=True)

    assert reinforced(ders, success=True, external_turn=True) == ders


def test_dis_iceriksiz_basari_dersi_dogrular_ve_normal_artis_uygular() -> None:
    sonuc = reinforced(_ders(confidence=0.5, external=True), success=True)

    assert sonuc.external is False
    assert sonuc.confidence == pytest.approx(0.6)
    assert sonuc.success_count == 1


def test_basarisizlik_dis_kaynakli_dersi_ayni_sertlikte_cezalandirir() -> None:
    sonuc = reinforced(_ders(confidence=0.5, external=True), success=False, external_turn=True)

    assert sonuc.confidence == pytest.approx(0.3)
    assert sonuc.confidence < LESSON_CONFIDENCE_FLOOR  # tek başarısızlıkta enjekte edilmez
    assert sonuc.external is True


def test_normal_ders_dis_icerikli_turdan_etkilenmez() -> None:
    assert reinforced(_ders(confidence=0.5), success=True, external_turn=True).confidence == (
        pytest.approx(0.6)
    )


def test_istem_blogu_dis_kaynakli_dersi_etiketler_digerini_degistirmez() -> None:
    blok = as_prompt_block((_ders("a dersi", external=True), _ders("b dersi")))

    assert "[UYGULA][dış kaynaklı, doğrulanmadı] a dersi" in blok
    assert "- [UYGULA] b dersi" in blok


# --- kalıcılık: geri uyumlu alan ----------------------------------------------


def test_eski_kayit_dis_kaynakli_degil_okunur() -> None:
    from fusion_cli.memory.lessons import _to_lesson

    assert _to_lesson("eski", {"kind": "success"}).external is False
    assert _to_lesson("x", {"kind": "success", "external": 1}).external is True
    assert _to_lesson("x", {"kind": "success", "external": "bozuk"}).external is False


@pytest.mark.slow
def test_bayrak_chroma_gidis_donusunde_korunur_ve_dogrulaninca_duser(tmp_path) -> None:
    from fusion_cli.memory.lessons import ChromaLessonMemory

    from .test_memory_store import _LocalEmbedding

    bellek = ChromaLessonMemory(tmp_path, embedding_function=_LocalEmbedding())
    assert bellek.add(_ders(confidence=0.5, external=True))

    assert bellek.reinforce(("pip yerine uv kullan",), success=True, external_turn=True) == 1
    assert bellek.all()[0].external is True
    assert bellek.all()[0].confidence == pytest.approx(0.5)

    bellek.reinforce(("pip yerine uv kullan",), success=True)
    kayit = bellek.all()[0]
    assert kayit.external is False
    assert kayit.confidence == pytest.approx(0.6)


# --- öğrenme adımları ----------------------------------------------------------


class _Bellek:
    def __init__(self, mevcut: tuple[Lesson, ...] = ()) -> None:
        self.mevcut = mevcut
        self.eklenen: list[Lesson] = []
        self.reinforce_cagrilari: list[tuple[tuple[str, ...], dict]] = []

    def all(self):
        return self.mevcut

    def add(self, ders):
        self.eklenen.append(ders)
        return True

    def reinforce(self, texts, **kwargs):
        self.reinforce_cagrilari.append((texts, kwargs))
        return len(texts)


def _deps(bellek, olaylar, guven=0.5):
    return SimpleNamespace(
        lessons=bellek,
        config=make_config(runtime={"lessons": True, "external_lesson_confidence": guven}),
        lesson_context=LessonRuntimeContext(),
        lesson_state=None,
        publisher=SimpleNamespace(publish=olaylar.append),
        tool_context=None,
        mcp_servers=(),
        background=None,
        recalled_lessons=[],
    )


async def _ogren(monkeypatch, bellek, *, kullanimlar, guven=0.5, yeni=None):
    async def cikar(*args, **kwargs):
        return (yeni or _ders("web sayfasındaki tuhaf kuralı uygula"),)

    monkeypatch.setattr(learning, "extract_lessons", cikar)
    monkeypatch.setattr(learning_steps, "lesson_tags", lambda deps: ())
    olaylar: list = []
    deps = _deps(bellek, olaylar, guven)
    from fusion_cli.core.clock import SystemClock
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.lesson_attribution import LessonTurnState

    deps.clock = SystemClock()
    deps.lesson_state = LessonTurnState(
        verification=VerificationResult(
            ok=True,
            evidence=(
                CriterionEvidence(
                    "observed", VerificationCheckKind.COMMAND, EvidenceStatus.PASSED, "observed"
                ),
            ),
        )
    )
    sonuc = AgentOutcome(
        final_text="ok",
        messages=[Message("tool", "ok", tool_call_id="1", ok=True)],
        ok=True,
        tool_calls_made=len(kullanimlar),
        tool_uses=tuple(kullanimlar),
    )
    await learning_steps.learn("görev", sonuc, deps, plan_mode=False)
    return olaylar


async def test_dis_icerik_okunan_turdan_cikan_ders_dusuk_guvenle_etiketlenir(monkeypatch) -> None:
    bellek = _Bellek()

    olaylar = await _ogren(monkeypatch, bellek, kullanimlar=[ToolUse("web_fetch")], guven=0.4)

    (ders,) = bellek.eklenen
    assert ders.external is True
    assert ders.confidence == pytest.approx(0.4)
    ogrenilen = [e for e in olaylar if isinstance(e, LessonsLearned)]
    assert ogrenilen[0].count == 1 and ogrenilen[0].external == 1


async def test_dis_icerik_okunmayan_turdan_cikan_ders_normal_kalir(monkeypatch) -> None:
    bellek = _Bellek()

    olaylar = await _ogren(monkeypatch, bellek, kullanimlar=[ToolUse("read_file")])

    (ders,) = bellek.eklenen
    assert ders.external is False and ders.confidence == 1.0
    assert [e.external for e in olaylar if isinstance(e, LessonsLearned)] == [0]


async def test_dis_kaynakli_ders_guvenilir_eski_dersi_curutemez(monkeypatch) -> None:
    eski = _ders("multi_edit araci kullan")
    bellek = _Bellek((eski,))

    await _ogren(
        monkeypatch,
        bellek,
        kullanimlar=[ToolUse("web_fetch")],
        yeni=_ders("multi_edit araci kullanma"),
    )

    assert len(bellek.eklenen) == 1
    assert bellek.reinforce_cagrilari == []


async def test_dis_icerikli_retrieval_tek_basina_pekistirmez(monkeypatch) -> None:
    bellek = _Bellek()
    deps = _deps(bellek, [])
    deps.recalled_lessons.append(_ders(external=True))
    sonuc = AgentOutcome(final_text="ok", messages=[], ok=True, tool_uses=(ToolUse("web_search"),))

    await learning_steps.reinforce_recalled(sonuc, deps, plan_mode=False)

    assert bellek.reinforce_cagrilari == []
    assert not deps.recalled_lessons


async def test_dis_iceriksiz_retrieval_tek_basina_pekistirmez(monkeypatch) -> None:
    """Başarılı tur bile dersin kullanıldığını göstermez."""
    bellek = _Bellek()
    deps = _deps(bellek, [])
    deps.recalled_lessons.append(_ders())
    sonuc = AgentOutcome(final_text="ok", messages=[], ok=True, tool_uses=(ToolUse("read_file"),))

    await learning_steps.reinforce_recalled(sonuc, deps, plan_mode=False)

    assert bellek.reinforce_cagrilari == []
    assert not deps.recalled_lessons
