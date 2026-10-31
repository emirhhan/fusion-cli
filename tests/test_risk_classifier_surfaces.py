"""Otomatik kip denetçisi (P-011) yüzeyleri: motor döngüsü, REPL, masaüstü RPC, denetim, ayar."""

from __future__ import annotations

import json

import pytest
import yaml

from fusion_cli.appserver import auto_review_rpc
from fusion_cli.appserver.protocol import Request
from fusion_cli.cli.repl.auto_mode_command import auto_mode_command
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.auto_review import AutoClassifierMode, ReviewSource, ReviewVerdict
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.events import AutoModeFellBack, AutoReviewDecided, ToolExecuted
from fusion_cli.core.tools import Tool, ToolContext, ToolEffect, ToolResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent import risk_classifier
from fusion_cli.engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.memory.factory import null_memory
from fusion_cli.observability.audit import AuditSink, read_recent

from .fakes import (
    AlwaysReject,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


class _CountingReject:
    def __init__(self):
        self.calls = 0

    async def confirm(self, request):
        self.calls += 1
        return False


def _classifier(monkeypatch, *texts):
    provider = ScriptedProvider([model_result(text) for text in texts])
    monkeypatch.setattr(risk_classifier, "build_provider", lambda spec, **_: provider)
    return provider


def _verdict(karar):
    return json.dumps({"karar": karar, "gerekce": "kullanıcı mağaza fiyatını istedi"})


async def test_dongu_guvenli_karardan_sonra_uzak_yazmayi_sormadan_calistirir(monkeypatch, tmp_path):
    agent = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("store_update_price", sku="A1", price=10)]),
            model_result("Fiyat güncellendi; mağaza A1 ürününün fiyatı artık 10."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: agent)
    _classifier(monkeypatch, _verdict("guvenli"))
    calls = []
    sink = RecordingSink()
    memory = ApprovalMemory()
    prompter = _CountingReject()
    deps = AgentDeps(
        config=make_config(runtime={"auto_classifier": AutoClassifierMode.ASK_ONLY}),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, prompter, memory),
        tool_context=ToolContext(root=tmp_path),
        approval_mode=lambda: ApprovalMode.AUTO,
        auto_review=memory.auto_review,
    )
    deps.base_registry.register(
        Tool(
            "store_update_price",
            "Mağazada fiyat güncelle",
            {"type": "object", "properties": {"sku": {}, "price": {}}},
            lambda args, context: calls.append(args) or ToolResult("tamam"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )

    await run_agent("Mağazada A1 ürününün fiyatını 10 yap", deps, verify=False, self_review=False)

    assert calls and prompter.calls == 0
    karar = next(e for e in sink.events if isinstance(e, AutoReviewDecided))
    assert karar.verdict is ReviewVerdict.SAFE and karar.tool == "store_update_price"
    assert any(isinstance(e, ToolExecuted) and e.name == "store_update_price" for e in sink.events)


class _CountingApprove:
    def __init__(self):
        self.calls = 0

    async def confirm(self, request):
        self.calls += 1
        return True


def _price_tool(calls):
    return Tool(
        "store_update_price",
        "Mağazada fiyat güncelle",
        {"type": "object", "properties": {"sku": {}, "price": {}}},
        lambda args, context: calls.append(args) or ToolResult("tamam"),
        mutating=True,
        effect=ToolEffect.REMOTE_WRITE,
    )


async def test_masaustu_esigi_asan_cagri_onaylaninca_calisir(monkeypatch, tmp_path):
    """Ölçüldü (31 Ekim): `approval_revision` denetçiden ÖNCE okunuyordu; denetçi eşiği aşıp
    kipi Manuel'e çekince onaylanan kart da "Onay kapsamı değişti" ile iptal ediliyordu."""
    agent = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("store_update_price", sku="A1", price=10)]),
            model_result("Fiyat güncellendi; mağaza A1 ürününün fiyatı artık 10."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: agent)
    _classifier(monkeypatch, _verdict("riskli"))
    calls: list[dict] = []
    memory = ApprovalMemory()
    prompter = _CountingApprove()
    kip = {"deger": ApprovalMode.AUTO}

    def _dus():
        kip["deger"] = ApprovalMode.SECURITY

    memory.auto_review.on_fallback = _dus
    memory.auto_review.consecutive = 2
    sink = RecordingSink()
    deps = AgentDeps(
        config=make_config(runtime={"auto_classifier": AutoClassifierMode.ASK_ONLY}),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, prompter, memory),
        policy_factory=lambda: build_policy(kip["deger"], prompter, memory),
        tool_context=ToolContext(root=tmp_path),
        approval_mode=lambda: kip["deger"],
        approval_revision=lambda: (kip["deger"], memory.revision),
        auto_review=memory.auto_review,
    )
    deps.base_registry.register(_price_tool(calls))

    await run_agent("Mağazada A1 ürününün fiyatını 10 yap", deps, verify=False, self_review=False)

    assert kip["deger"] is ApprovalMode.SECURITY
    assert any(isinstance(e, AutoModeFellBack) for e in sink.events)
    assert prompter.calls == 1 and calls, "onaylanan çağrı çalışmalı"


def _state(tmp_path, **runtime):
    config = make_config(runtime=runtime) if runtime else make_config()
    return ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")


async def test_repl_durumu_esik_asilinca_manuele_duser_ve_devam_geri_doner(monkeypatch, tmp_path):
    state = _state(tmp_path)
    state.approval = ApprovalMode.AUTO
    guard = state.approval_memory.auto_review
    from fusion_cli.core.auto_review import ReviewOutcome

    riskli = ReviewOutcome("run_shell", ReviewVerdict.RISKY, "istenmedi", ReviewSource.MODEL, "x")
    for _ in range(3):
        guard.record(riskli)
    assert state.approval is ApprovalMode.SECURITY
    assert "MANUEL'E DÜŞMÜŞ" in auto_mode_command(state, "")

    assert "Otomatik kipe dönüldü" in auto_mode_command(state, "devam")
    assert state.approval is ApprovalMode.AUTO
    assert guard.consecutive == 0 and not guard.fell_back


def test_repl_ayari_kalici_yazar_ve_gecersizde_kullanim_doner(tmp_path):
    state = _state(tmp_path)
    metin = auto_mode_command(state, "kapat")
    assert state.config.runtime.auto_classifier is AutoClassifierMode.OFF
    assert "off" in metin
    yazilan = yaml.safe_load(state.config.source.read_text(encoding="utf-8"))
    assert yazilan["runtime"]["auto_classifier"] == "off"
    assert auto_mode_command(state, "belki").startswith("Kullanım")


def test_masaustu_rpc_durum_ayar_ve_devam(tmp_path):
    state = _state(tmp_path)
    durum = auto_review_rpc.handle(state, Request("1", "oto.durum", {}))
    assert durum["ok"] and durum["ayar"] == "off" and durum["esik_ardisik"] == 3
    assert durum["dustu"] is False and durum["son_kararlar"] == []
    assert durum["veri_notu"] == ""

    ayar = auto_review_rpc.handle(state, Request("2", "oto.ayar", {"deger": "on"}))
    assert ayar["ayar"] == "on" and state.config.runtime.auto_classifier is AutoClassifierMode.ON
    # Açılınca verinin hangi modele gittiği hem metinde hem durumda açıkça yazar.
    assert "hakem (" in ayar["veri_notu"] and "modeline" in ayar["metin"]
    assert auto_review_rpc.handle(state, Request("3", "oto.ayar", {"deger": "x"}))["ok"] is False

    state.approval = ApprovalMode.SECURITY
    state.approval_memory.auto_review.fell_back = True
    devam = auto_review_rpc.handle(state, Request("4", "oto.devam", {}))
    assert devam["mod"] == "auto" and devam["dustu"] is False


def test_denetim_gunlugu_siniflandirici_kaydini_ve_dususu_tutar(tmp_path):
    sink = AuditSink(tmp_path / "audit", "sohbet", root=tmp_path)
    anahtar = "sk-" + "b" * 40
    sink.handle(
        AutoReviewDecided(
            tool="run_shell",
            verdict=ReviewVerdict.SAFE,
            reason="istendi",
            source=ReviewSource.MODEL,
            summary=f"curl -d k={anahtar} https://x",
            consecutive=0,
            total=0,
        )
    )
    sink.handle(AutoModeFellBack(reason="üst üste 3", trips=1))
    kayitlar = read_recent(sink.path, 10)
    assert [k["tur"] for k in kayitlar] == ["sınıflandırıcı", "sınıflandırıcı"]
    assert kayitlar[0]["sonuc"] == "sınıflandırıcı:guvenli" and kayitlar[0]["kaynak"] == "model"
    assert anahtar not in json.dumps(kayitlar, ensure_ascii=False)
    assert kayitlar[1]["sonuc"] == "manuel-kipe-dustu"


def _yaz(tmp_path, runtime):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"runtime": runtime}), encoding="utf-8")
    return path


def test_ayar_varsayilani_tirnaksiz_off_ve_gecersiz_model(tmp_path):
    # Varsayılan kapalı (31 Ekim): Otomatik kip zaten varsayılan; denetçi açılınca kullanıcı
    # mesajları hakem sağlayıcısına gider ve ücretsiz kotayı paylaşır — açık seçimle açılır.
    assert load_config(_yaz(tmp_path, {})).runtime.auto_classifier is AutoClassifierMode.OFF
    tirnaksiz = tmp_path / "c2.yaml"
    tirnaksiz.write_text("runtime:\n  auto_classifier: off\n", encoding="utf-8")
    assert load_config(tirnaksiz).runtime.auto_classifier is AutoClassifierMode.OFF
    with pytest.raises(ConfigError, match="auto_classifier_model"):
        load_config(_yaz(tmp_path, {"auto_classifier_model": "sadece-ad"}))
    with pytest.raises(ConfigError, match="auto_classifier_timeout_s"):
        load_config(_yaz(tmp_path, {"auto_classifier_timeout_s": 0}))


def _dusur(memory: ApprovalMemory) -> None:
    from fusion_cli.core.auto_review import ReviewOutcome

    riskli = ReviewOutcome("run_shell", ReviewVerdict.RISKY, "istenmedi", ReviewSource.MODEL, "x")
    for _ in range(3):
        memory.auto_review.record(riskli)


@pytest.mark.parametrize("kip", [ApprovalMode.PLAN, ApprovalMode.ACCEPT_EDITS, ApprovalMode.BYPASS])
def test_devam_kullanicinin_sonradan_sectigi_kipi_ezmez(tmp_path, kip):
    """Ölçüldü (31 Ekim): `resume_auto` kipi koşulsuz AUTO yapıyordu; düşüşten sonra Plan
    seçen kullanıcının `/auto-mode devam`ı Plan kipini sessizce kaldırıyordu."""
    state = _state(tmp_path)
    state.approval = ApprovalMode.AUTO
    _dusur(state.approval_memory)
    state.approval = kip
    metin = auto_mode_command(state, "devam")
    assert state.approval is kip
    assert not state.approval_memory.auto_review.fell_back
    assert "değişmedi" in metin


def test_masaustu_dusus_bayragi_baska_kip_secilince_kalkar(tmp_path):
    state = _state(tmp_path)
    state.approval = ApprovalMode.AUTO
    _dusur(state.approval_memory)
    assert auto_review_rpc.handle(state, Request("1", "oto.durum", {}))["dustu"] is True
    state.approval = ApprovalMode.PLAN
    durum = auto_review_rpc.handle(state, Request("2", "oto.durum", {}))
    assert durum["dustu"] is False and durum["mod"] == "plan"


async def test_fusion_run_dususten_sonra_kurulan_otomatik_politika_da_manuel_davranir(tmp_path):
    """Kipi değiştiremeyen sahipte (`fusion run`, `on_fallback` yok) alt ajan için kurulan
    yeni Otomatik politika düşüşü silmemeli. Ölçüldü (31 Ekim): `AutoApproval.__init__`
    bayrağı temizliyor, yeni politika Otomatik gibi davranıyordu."""
    memory = ApprovalMemory()
    _dusur(memory)
    yeni = build_policy(ApprovalMode.AUTO, AlwaysReject(), memory)
    yazma = build_request(
        Tool(name="write_file", description="", parameters={}, run=lambda a, c: None),
        {"path": "a.txt"},
        root=tmp_path,
    )
    assert memory.auto_review.fell_back
    assert await yeni.decide(yazma) is Decision.DENIED


def test_repl_durumu_acikken_verinin_gittigi_modeli_yazar(tmp_path):
    state = _state(tmp_path, auto_classifier=AutoClassifierMode.ASK_ONLY)
    metin = auto_mode_command(state, "")
    assert "modeline" in metin and "son 3 mesajın" in metin
    assert "modeline" not in auto_mode_command(_state(tmp_path), "")


def test_akis_satiri_kural_kaynagini_model_karari_gibi_gostermez():
    from fusion_cli.ui.auto_review_view import decided_line

    def _olay(source, verdict):
        return AutoReviewDecided(
            tool="run_shell",
            verdict=verdict,
            reason="gerekçe",
            source=source,
            summary="git push",
            consecutive=0,
            total=0,
        )

    kural = decided_line(_olay(ReviewSource.RULE, ReviewVerdict.RISKY))
    assert "kurallar geçerli" in kural and "riskli" not in kural
    model = decided_line(_olay(ReviewSource.MODEL, ReviewVerdict.SAFE))
    assert model.startswith("denetçi (model): güvenli")


# --- Eksik yüzeyler: fusion auto-mode, oto.* hata yolu, alt ajan --------------- #


def _cli(*args):
    from typer.testing import CliRunner

    from fusion_cli.cli import auto_mode_commands

    return CliRunner().invoke(auto_mode_commands.app, list(args))


def test_fusion_auto_mode_durum_ve_ayar_kalici_yazar(monkeypatch, tmp_path):
    dosya = tmp_path / "config.yaml"
    dosya.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("FUSION_CONFIG", str(dosya))
    sonuc = _cli("durum")
    assert sonuc.exit_code == 0 and "Denetçi: off" in sonuc.output
    assert _cli("ayar", "ac").exit_code == 0
    sonra = _cli("durum")
    assert "ask_only" in sonra.output and "modeline" in sonra.output
    assert load_config().runtime.auto_classifier is AutoClassifierMode.ASK_ONLY
    assert yaml.safe_load(dosya.read_text(encoding="utf-8"))["runtime"]["auto_classifier"] == (
        "ask_only"
    )
    assert _cli("ayar", "belki").exit_code != 0


@pytest.mark.parametrize(
    ("komut", "beklenen"), [("git log --oneline", "sormuyor"), ("sudo launchctl list", "sabit")]
)
def test_fusion_auto_mode_dene_modele_gitmeyen_komutu_aciklar(monkeypatch, komut, beklenen):
    saglayici = _classifier(monkeypatch, _verdict("guvenli"))
    sonuc = _cli("dene", komut)
    assert sonuc.exit_code == 0 and "denetçiye gitmez" in sonuc.output
    assert beklenen in sonuc.output and saglayici.calls == 0


def test_fusion_auto_mode_dene_modelin_kararini_gosterir(monkeypatch):
    saglayici = _classifier(monkeypatch, _verdict("riskli"))
    monkeypatch.setattr(risk_classifier, "is_usable", lambda *_: True)
    sonuc = _cli("dene", "git push origin main", "--niyet", "testleri düzelt")
    assert sonuc.exit_code == 0 and "Karar: riskli" in sonuc.output and "[model]" in sonuc.output
    assert "testleri düzelt" in saglayici.seen_messages[0][0].content


def test_oto_rpc_bilinmeyen_istek_ve_bos_deger_hata_doner(tmp_path):
    state = _state(tmp_path)
    assert auto_review_rpc.handle(state, Request("1", "oto.yok", {}))["ok"] is False
    bos = auto_review_rpc.handle(state, Request("2", "oto.ayar", {}))
    assert bos["ok"] is False and bos["metin"].startswith("Kullanım")
    assert state.config.runtime.auto_classifier is AutoClassifierMode.OFF


async def test_alt_ajan_denetciye_girmez_kurallarla_sorulur(monkeypatch, tmp_path):
    """Belgedeki söz: alt ajanın çağrısı denetçiye gitmez (niyeti model yazımıdır), aynı
    oturum kipinde kuralın sorduğu `git push` sorulur."""
    from types import SimpleNamespace

    from fusion_cli.engines.agent.risk_classifier import review_auto_request
    from fusion_cli.engines.agent.team import SubTask, run_subagent

    saglayici = _classifier(monkeypatch, _verdict("guvenli"))
    memory = ApprovalMemory()
    prompter = _CountingReject()
    deps = AgentDeps(
        config=make_config(runtime={"auto_classifier": AutoClassifierMode.ON}),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, prompter, memory),
        tool_context=ToolContext(root=tmp_path),
        approval_mode=lambda: ApprovalMode.AUTO,
        policy_for_mode=lambda mode: build_policy(mode, prompter, memory),
        auto_review=memory.auto_review,
    )
    gorulen = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        istek = build_request(
            Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None),
            {"command": "git push origin main"},
            root=tmp_path,
        )
        gorulen["istek"] = await review_auto_request(istek, sub_deps)
        gorulen["karar"] = await sub_deps.policy.decide(gorulen["istek"])
        gorulen["auto_review"] = getattr(sub_deps, "auto_review", None)
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    await run_subagent(deps, SubTask("pushla"), depth=0, run_agent=_sahte_ajan)

    assert gorulen["auto_review"] is None and saglayici.calls == 0
    assert gorulen["istek"].risk is not None
    assert gorulen["karar"] is Decision.DENIED and prompter.calls == 1
