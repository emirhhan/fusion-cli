"""Kapı iki düzeltmeden sonra da kırmızıysa tek ek tur üst modelle koşar (yol haritası 6)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.config.model_select import (
    EscalationSource,
    escalation_target,
    select_agent_spec,
)
from fusion_cli.config.models import TierSpec, WebSessionConfig
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.events import GateEscalated, GateEscalationFinished, StatusChanged
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

TAM_CEVAP = "Görevi tamamladım; ilgili değişiklik `a.html:1` satırında yapıldı ve doğrulandı."

SUPER_NIM = "nvidia_nim/x/super"
SUPER_OR = "openrouter/x/super:free"
ULTRA_NIM = "nvidia_nim/x/ultra"
ULTRA_OR = "openrouter/x/ultra:free"


def _zincir(*fallback: str) -> ModelSpec:
    return ModelSpec(name="super", model=SUPER_NIM, tags=("code", "agent"), fallback=fallback)


def _kademeli(agent: ModelSpec, *, runtime: dict | None = None, **ek):
    """low -> medium -> ultra merdiveni (defaults.yaml ile aynı kurgu)."""
    judge = ModelSpec(name="hakem", model=SUPER_NIM)
    ultra_baslik = ModelSpec(name="ultra", model=ULTRA_NIM, tags=("code", "agent"))
    medium = ModelSpec(name="nano", model="nvidia_nim/x/nano", tags=("code",))
    tiers = (
        TierSpec("low", "low", agent, judge, (agent,)),
        TierSpec("medium", "medium", medium, judge, (medium,)),
        TierSpec("ultra", "ultra", ultra_baslik, judge, (ultra_baslik,)),
    )
    return make_config(agent=agent, tiers=tiers, task_model_map={}, runtime=runtime or {}, **ek)


def _varsayilan_zincir() -> ModelSpec:
    return _zincir(SUPER_OR, ULTRA_NIM, ULTRA_OR)


# --- saf seçim ---------------------------------------------------------------- #


def test_zincirdeki_ust_kademe_secilir_ve_kopyalariyla_sinirlanir():
    config = _kademeli(_varsayilan_zincir())

    hedef = escalation_target(config, select_agent_spec(config, "general"))

    assert hedef is not None
    assert hedef.source is EscalationSource.TIER and hedef.tier == "ultra"
    assert hedef.spec.model == ULTRA_NIM
    # Sağlayıcı arızasında zayıf modele (super) DÖNÜLMEZ; yalnız ultra'nın kopyası.
    assert hedef.spec.fallback == (ULTRA_OR,)


def test_ust_model_zincirde_yoksa_hicbir_sey_yapilmaz():
    # Yalnız super'in sağlayıcı kopyaları: sağlayıcı tercihi/anahtar budaması ultra'yı
    # zincirden çıkarmış kullanıcı. Yeni sağlayıcı/model uydurulmaz.
    config = _kademeli(_zincir(SUPER_OR))

    assert escalation_target(config, select_agent_spec(config, "general")) is None


def test_ucretli_openrouter_modeli_otomatik_secilmez():
    agent = _zincir("openrouter/x/ultra")  # `:free` eki yok -> ücretli
    config = _kademeli(agent)
    paid = ModelSpec(name="ultra", model="openrouter/x/ultra")
    config = replace(
        config,
        tiers=(config.tiers[0], TierSpec("ultra", "u", paid, paid, (paid,))),
    )

    assert escalation_target(config, select_agent_spec(config, "general")) is None


def test_yerel_model_merdivende_degilse_yukseltme_yok():
    config = _kademeli(_varsayilan_zincir())
    yerel = replace(config, agent=ModelSpec(name="yerel", model="ollama/qwen3.5-9b"))

    assert escalation_target(yerel, yerel.agent) is None


def test_strict_secimde_yukseltme_yok():
    agent = replace(_varsayilan_zincir(), tags=("strict",))
    config = _kademeli(agent)

    assert escalation_target(config, agent) is None


def test_ayar_kapaliysa_yukseltme_yok():
    config = _kademeli(_varsayilan_zincir(), runtime={"escalate_on_gate_failure": False})

    assert escalation_target(config, select_agent_spec(config, "general")) is None


def test_acik_ayar_kademeden_once_gelir():
    config = _kademeli(_varsayilan_zincir(), runtime={"escalation_model": "ollama/guclu-yerel-70b"})

    hedef = escalation_target(config, select_agent_spec(config, "general"))

    assert hedef is not None
    assert hedef.source is EscalationSource.SETTING
    assert hedef.spec.model == "ollama/guclu-yerel-70b" and hedef.spec.fallback == ()


def test_acik_ayar_zincirde_kullanilmayan_yonetilen_saglayiciya_cikmaz():
    # Kullanıcı OpenRouter'ı dışlamış (zincirde yalnız NIM): açık ayar bunu geri açamaz.
    agent = ModelSpec(name="super", model=SUPER_NIM, fallback=(ULTRA_NIM,))
    config = _kademeli(agent, runtime={"escalation_model": "openrouter/y/buyuk:free"})

    assert escalation_target(config, agent) is not None  # kademe yolu (ultra) hâlâ çalışır
    config = replace(config, tiers=())
    assert escalation_target(config, agent) is None


@pytest.mark.parametrize(
    "model",
    ["gemini_web/hesap/auto", "codex_cli/default", "nvidia_nim/x/super"],
)
def test_acik_ayar_web_codex_ve_ayni_modeli_reddeder(model):
    config = _kademeli(_varsayilan_zincir(), runtime={"escalation_model": model})
    config = replace(config, tiers=())

    assert escalation_target(config, select_agent_spec(config, "general")) is None


def test_web_oturumu_olan_model_acik_ayarla_bile_secilmez():
    oturum = WebSessionConfig(provider="special", account="a", model="ozel/web-modeli")
    config = _kademeli(_varsayilan_zincir(), runtime={"escalation_model": "ozel/web-modeli"})
    config = replace(config, tiers=(), web_sessions=(oturum,))

    assert escalation_target(config, select_agent_spec(config, "general")) is None


def test_gercek_varsayilanlarda_dusuk_kademe_ultra_a_yukselir(tmp_path):
    dosya = tmp_path / "config.yaml"
    dosya.write_text("{}\n", encoding="utf-8")
    config = load_config(dosya)

    hedef = escalation_target(config, select_agent_spec(config, "general"))

    assert config.runtime.escalate_on_gate_failure is True
    assert config.runtime.escalation_model == ""
    assert hedef is not None and hedef.tier == "ultra"
    assert hedef.spec.model == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"
    assert hedef.spec.fallback == ("openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",)


def test_gecersiz_yukseltme_modeli_yuklemede_reddedilir(tmp_path):
    dosya = tmp_path / "config.yaml"
    dosya.write_text("runtime:\n  escalation_model: ultra\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="escalation_model"):
        load_config(dosya)


# --- döngü -------------------------------------------------------------------- #


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


class _SiraliDogrulayici:
    """Verilen sonuçları sırayla döndürür; bittiğinde sonuncuyu tekrarlar."""

    def __init__(self, *sonuclar):
        self._sonuclar = list(sonuclar)
        self.calls = 0

    async def verify(self):
        self.calls += 1
        index = min(self.calls, len(self._sonuclar)) - 1
        return self._sonuclar[index]


KIRMIZI = VerificationResult(ok=False, summary="test düştü", findings=("test_a başarısız",))
YESIL = VerificationResult(ok=True)


class _Gozlemci:
    """Modeli çağıran spec'i kaydeden sarmalayıcı; yanıtlar ortak betikten gelir."""

    def __init__(self, spec, betik, gorulen):
        self._spec = spec
        self._betik = betik
        self._gorulen = gorulen

    @property
    def label(self):
        return self._spec.model

    async def complete(self, request):
        self._gorulen.append(self._spec.model)
        return await self._betik.complete(request)

    async def stream(self, request):
        self._gorulen.append(self._spec.model)
        async for parca in self._betik.stream(request):
            yield parca


def _kur(monkeypatch, betik):
    gorulen: list[str] = []

    def _build(spec, *, publisher=None, **kwargs):
        return _Gozlemci(spec, betik, gorulen)

    monkeypatch.setattr(agent_loop, "build_provider", _build)
    return gorulen


def _deps(tmp_path, sink, config):
    deps = AgentDeps(
        config=config,
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return deps


def _yaz(surum: int):
    return model_result(tool_calls=[tool_call("write_file", path="a.html", content=f"<h1>{surum}")])


def _betik(tur_sayisi: int):
    """Ana tur + `tur_sayisi` düzeltme: her tur bir gerçek yazma ve kısa cevap."""
    sonuclar = [_yaz(0), model_result(TAM_CEVAP)]
    for surum in range(1, tur_sayisi + 1):
        sonuclar += [_yaz(surum), model_result(TAM_CEVAP)]
    return ScriptedProvider(sonuclar)


def _olaylar(sink, tip):
    return [olay for olay in sink.events if isinstance(olay, tip)]


async def test_iki_duzeltmeden_sonra_kirmizi_kalan_kapi_ust_modelle_bir_tur_alir(
    monkeypatch, tmp_path
):
    sink = RecordingSink()
    gorulen = _kur(monkeypatch, _betik(3))
    dogrulayici = _SiraliDogrulayici(KIRMIZI, KIRMIZI, KIRMIZI, YESIL)
    deps = _deps(tmp_path, sink, _kademeli(_varsayilan_zincir()))
    deps.verifier = dogrulayici

    sonuc = await run_agent("a.html yaz", deps)

    # Ana tur super; iki düzeltme AYNI modelin ilk yedeği; ek tur ultra (iki model çağrısı).
    assert gorulen[:2] == [SUPER_NIM, SUPER_NIM]
    assert set(gorulen[2:6]) == {SUPER_OR}
    assert gorulen[6:] == [ULTRA_NIM, ULTRA_NIM]
    assert dogrulayici.calls == 4
    (baslangic,) = _olaylar(sink, GateEscalated)
    assert (baslangic.failed_rounds, baslangic.from_model, baslangic.to_model) == (
        2,
        SUPER_NIM,
        ULTRA_NIM,
    )
    assert baslangic.source == "kademe" and baslangic.findings == 1
    (bitis,) = _olaylar(sink, GateEscalationFinished)
    assert bitis.gate_ok is True and bitis.measured is True and bitis.model == ULTRA_NIM
    durumlar = [olay.message for olay in _olaylar(sink, StatusChanged)]
    assert any("Doğrulama 2 kez başarısız" in m and ULTRA_NIM in m for m in durumlar)
    assert "kapı geçti" in sonuc.final_text
    assert sonuc.ok is True


async def test_ust_modelden_sonra_da_kirmizi_kalirsa_tur_basarisiz_ve_ek_tur_tektir(
    monkeypatch, tmp_path
):
    sink = RecordingSink()
    gorulen = _kur(monkeypatch, _betik(5))
    dogrulayici = _SiraliDogrulayici(KIRMIZI)
    deps = _deps(tmp_path, sink, _kademeli(_varsayilan_zincir()))
    deps.verifier = dogrulayici

    sonuc = await run_agent("a.html yaz", deps)

    assert len(_olaylar(sink, GateEscalated)) == 1
    assert _olaylar(sink, GateEscalationFinished)[0].gate_ok is False
    assert gorulen.count(ULTRA_NIM) == 2  # tek ek tur: araç çağrısı + kapanış
    assert dogrulayici.calls == 4  # 2 doğrula+düzelt, son ölçüm, ek turdan sonraki ölçüm
    assert sonuc.ok is False
    assert "ek deneme de kapıyı geçemedi" in sonuc.final_text


async def test_kapi_ilk_duzeltmede_yesile_donerse_yukseltme_olmaz(monkeypatch, tmp_path):
    sink = RecordingSink()
    gorulen = _kur(monkeypatch, _betik(2))
    deps = _deps(tmp_path, sink, _kademeli(_varsayilan_zincir()))
    deps.verifier = _SiraliDogrulayici(KIRMIZI, YESIL)

    await run_agent("a.html yaz", deps)

    assert not _olaylar(sink, GateEscalated)
    assert ULTRA_NIM not in gorulen


async def test_ust_model_tanimli_degilse_davranis_eskisi_gibi_kalir(monkeypatch, tmp_path):
    sink = RecordingSink()
    gorulen = _kur(monkeypatch, _betik(5))
    dogrulayici = _SiraliDogrulayici(KIRMIZI)
    deps = _deps(tmp_path, sink, _kademeli(_zincir(SUPER_OR)))  # ultra zincirde yok
    deps.verifier = dogrulayici

    sonuc = await run_agent("a.html yaz", deps)

    assert not _olaylar(sink, GateEscalated)
    assert dogrulayici.calls == 3  # 2 doğrula+düzelt + son ölçüm (A2-01)
    assert ULTRA_NIM not in gorulen
    assert sonuc.ok is False


async def test_ayar_kapaliyken_yukseltme_olmaz(monkeypatch, tmp_path):
    sink = RecordingSink()
    gorulen = _kur(monkeypatch, _betik(5))
    config = _kademeli(_varsayilan_zincir(), runtime={"escalate_on_gate_failure": False})
    deps = _deps(tmp_path, sink, config)
    deps.verifier = _SiraliDogrulayici(KIRMIZI)

    await run_agent("a.html yaz", deps)

    assert not _olaylar(sink, GateEscalated)
    assert ULTRA_NIM not in gorulen


async def test_acik_yukseltme_modeli_kullanilir(monkeypatch, tmp_path):
    sink = RecordingSink()
    gorulen = _kur(monkeypatch, _betik(3))
    config = _kademeli(_zincir(SUPER_OR), runtime={"escalation_model": "ollama/guclu-70b"})
    deps = _deps(tmp_path, sink, config)
    deps.verifier = _SiraliDogrulayici(KIRMIZI, KIRMIZI, KIRMIZI, YESIL)

    await run_agent("a.html yaz", deps)

    (olay,) = _olaylar(sink, GateEscalated)
    assert olay.source == "ayar" and olay.to_model == "ollama/guclu-70b"
    assert gorulen[-2:] == ["ollama/guclu-70b", "ollama/guclu-70b"]


async def test_ust_model_hata_verirse_zayif_modelle_yeniden_denenmez(monkeypatch, tmp_path):
    sink = RecordingSink()
    betik = ScriptedProvider(
        [_yaz(0), model_result(TAM_CEVAP)]
        + [_yaz(1), model_result(TAM_CEVAP), _yaz(2), model_result(TAM_CEVAP)]
        + [model_result("", ok=False, error="400 bad request") for _ in range(6)]
    )
    gorulen = _kur(monkeypatch, betik)
    deps = _deps(tmp_path, sink, _kademeli(_varsayilan_zincir()))
    deps.verifier = _SiraliDogrulayici(KIRMIZI)

    sonuc = await run_agent("a.html yaz", deps)

    ek_tur = gorulen[6:]
    assert ek_tur and set(ek_tur) == {ULTRA_NIM}
    assert sonuc.ok is False
