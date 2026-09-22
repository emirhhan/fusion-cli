"""`ask_teacher` aracı — web öğretmene tek-soru danışma (Faz 4, Görev 1)."""

from __future__ import annotations

from pathlib import Path

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
