"""`ask_teacher` aracı — web öğretmene tek-soru danışma (Faz 4, Görev 1)."""

from __future__ import annotations

from pathlib import Path

import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelResult, ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.engines.agent.loop import AgentDeps

from .fakes import AlwaysApprove, make_config


class _Publisher:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


async def _hicbir_alt_ajan(*args, **kwargs):  # pragma: no cover - çağrılmaz
    raise AssertionError("alt ajan çalışmamalı")


def _deps(tmp_path, publisher=None, **overrides):
    return AgentDeps(
        config=make_config(**overrides),
        publisher=publisher or _Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _registry(deps):
    return build_agent_registry(deps, depth=0, run_agent=_hicbir_alt_ajan)


class _OgretmenSaglayici:
    def __init__(self, text="teşhis: yol biçimi yanlış, 'res://' önekini kaldır."):
        self.text = text
        self.seen = []

    @property
    def label(self):
        return "sahte-ogretmen"

    async def complete(self, request):
        self.seen.append(request)
        return ModelResult(
            name="ogretmen", model="sahte/ogretmen", text=self.text, latency_ms=1, ok=True
        )


def _ogretmen(monkeypatch, saglayici):
    def _build(spec, **kwargs):
        del spec, kwargs
        return saglayici

    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", _build)


def test_ogretmen_yoksa_arac_hic_sunulmaz(tmp_path):
    deps = _deps(tmp_path, teacher=None)

    assert _registry(deps).get("ask_teacher") is None


def test_ogretmen_varsa_arac_sunulur(tmp_path):
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    assert _registry(deps).get("ask_teacher") is not None


def test_kayitli_web_oturumu_ajanin_ogretmen_aracini_acar(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"web_sessions": [{
        "provider": "gemini_web", "model": "gemini_web/main/auto",
        "login_verified": True, "enabled": True,
    }]}), encoding="utf-8")
    deps = _deps(tmp_path)
    deps.config = load_config(path)

    assert _registry(deps).get("ask_teacher") is not None


async def test_soru_bos_olamaz(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    sonuc = await _registry(deps).execute("ask_teacher", {"question": "  "}, deps.tool_context)

    assert sonuc.ok is False
    assert not saglayici.seen


async def test_ogretmenin_cevabi_donulur_ve_olay_yayinlanir(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    publisher = _Publisher()
    deps = _deps(
        tmp_path, publisher=publisher, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen")
    )

    sonuc = await _registry(deps).execute(
        "ask_teacher",
        {
            "question": "bu hata neden sürüyor?",
            "durum": "dosya yazılamıyor",
            "denenenler": "3 kez denedim",
        },
        deps.tool_context,
    )

    assert sonuc.ok is True
    assert "yol biçimi yanlış" in sonuc.output
    from fusion_cli.core.events import TeacherConsulted

    olaylar = [e for e in publisher.events if isinstance(e, TeacherConsulted)]
    assert len(olaylar) == 1
    assert olaylar[0].question == "bu hata neden sürüyor?"
    assert olaylar[0].brief_truncated is False


async def test_gonderilen_brief_durum_ve_denenenleri_icerir(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    await _registry(deps).execute(
        "ask_teacher",
        {"question": "soru", "durum": "ÖZEL_DURUM_METNİ", "denenenler": "ÖZEL_DENEME_METNİ"},
        deps.tool_context,
    )

    gonderilen = saglayici.seen[0].messages[0].content
    assert "ÖZEL_DURUM_METNİ" in gonderilen
    assert "ÖZEL_DENEME_METNİ" in gonderilen


async def test_dokunulan_dosyalar_brief_e_otomatik_eklenir(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))
    deps.tool_context.touched.add(Path(tmp_path / "src" / "a.py"))
    deps.tool_context.fully_read.add(Path(tmp_path / "src" / "b.py"))

    await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    gonderilen = saglayici.seen[0].messages[0].content
    assert "a.py" in gonderilen
    assert "b.py" in gonderilen


class _SahteDersBellegi:
    def __init__(self, *, recall_sonucu=()):
        self._recall_sonucu = recall_sonucu
        self.eklenenler = []

    def add(self, lesson):
        self.eklenenler.append(lesson)
        return True

    def recall(self, task, limit=4, *, scope=None, workspace=None, tags=()):
        return self._recall_sonucu

    def reinforce(self, texts, *, success):
        raise AssertionError("reinforce çağrılmamalı")


def test_teacherless_acikken_arac_hic_sunulmaz(tmp_path):
    deps = _deps(
        tmp_path,
        teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"),
        runtime={"teacherless": True},
    )

    assert _registry(deps).get("ask_teacher") is None


def test_teacherless_kapaliyken_council_etkilenmez(tmp_path):
    """`teacherless` yalnız `ask_teacher`'ı kapatır; `council` HER ZAMAN sunulur."""
    deps = _deps(tmp_path, teacher=None, runtime={"teacherless": True})

    assert _registry(deps).get("council") is not None


async def test_basarili_cevap_ogretmen_defterine_yazilir(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    await _registry(deps).execute(
        "ask_teacher", {"question": "soru", "durum": "ÖZEL_DURUM"}, deps.tool_context
    )

    gunluk = tmp_path / ".fusion" / "ogretmen.md"
    assert gunluk.exists()
    icerik = gunluk.read_text(encoding="utf-8")
    assert "soru" in icerik
    assert "ÖZEL_DURUM" in icerik


async def test_lessons_yoksa_defter_yine_yazilir_cokme_olmaz(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))
    assert deps.lessons is None

    sonuc = await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert sonuc.ok is True
    assert (tmp_path / ".fusion" / "ogretmen.md").exists()


async def test_lesson_sync_acikken_derse_yazilir(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici(text="wc -l ile satır say")
    _ogretmen(monkeypatch, saglayici)
    bellek = _SahteDersBellegi()
    deps = _deps(
        tmp_path,
        teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"),
        runtime={"teacher_lesson_sync": True},
    )
    deps.lessons = bellek

    await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert len(bellek.eklenenler) == 1
    icerik = (tmp_path / ".fusion" / "ogretmen.md").read_text(encoding="utf-8")
    assert "Ders belleğe kaydedildi" in icerik


async def test_lesson_sync_kapaliyken_derse_yazilmaz(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    bellek = _SahteDersBellegi()
    deps = _deps(
        tmp_path,
        teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"),
        runtime={"teacher_lesson_sync": False},
    )
    deps.lessons = bellek

    await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert bellek.eklenenler == []


async def test_catisma_bulununca_kullaniciya_gorunur_not_eklenir(tmp_path, monkeypatch):
    from fusion_cli.core.memory import Lesson, LessonKind, LessonSource

    saglayici = _OgretmenSaglayici(text="run_shell KULLANMA, riskli")
    _ogretmen(monkeypatch, saglayici)
    mevcut = Lesson(text="run_shell kullan", kind=LessonKind.SUCCESS, source=LessonSource.LEARNED)
    bellek = _SahteDersBellegi(recall_sonucu=(mevcut,))
    deps = _deps(
        tmp_path,
        teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"),
        runtime={"teacher_lesson_sync": True},
    )
    deps.lessons = bellek

    sonuc = await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert bellek.eklenenler == []
    assert "çelişebilir" in sonuc.output
    assert "teacher-lesson-sync" in sonuc.output
    icerik = (tmp_path / ".fusion" / "ogretmen.md").read_text(encoding="utf-8")
    assert "kaydedilmedi" in icerik


async def test_basarili_cagri_butce_dosyasi_olusturur(tmp_path, monkeypatch):
    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert (tmp_path / ".fusion" / "ogretmen-butce.json").exists()


async def test_butce_dolunca_aga_hic_baglanilmaz(tmp_path, monkeypatch):
    import fusion_cli.engines.agent.teacher_budget as teacher_budget
    from fusion_cli.engines.agent.teacher_budget import BudgetCheck

    saglayici = _OgretmenSaglayici()
    _ogretmen(monkeypatch, saglayici)
    monkeypatch.setattr(
        teacher_budget,
        "check_and_spend",
        lambda *a, **k: BudgetCheck(allowed=False, used=60, limit=60, reset_in_s=120.0),
    )
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    sonuc = await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert sonuc.ok is False
    assert "bütçe" in sonuc.output.lower()
    assert saglayici.seen == []


async def test_ogretmene_ulasilamazsa_anlasilir_hata_doner(tmp_path, monkeypatch):
    class _Basarisiz:
        @property
        def label(self):
            return "sahte-basarisiz"

        async def complete(self, request):
            del request
            return ModelResult(
                name="ogretmen",
                model="sahte/ogretmen",
                text="",
                latency_ms=1,
                ok=False,
                error="oturum kilitli",
            )

    _ogretmen(monkeypatch, _Basarisiz())
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    sonuc = await _registry(deps).execute("ask_teacher", {"question": "soru"}, deps.tool_context)

    assert sonuc.ok is False
    assert "oturum kilitli" in sonuc.output
