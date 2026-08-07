"""Tur bütçesi — sayaçların tek yerde birikmesi ve döngü kapıları.

Bu dosyanın varlık sebebi ölçülmüş bir hatadır: bütçe sayaçları `_drive`'ın yerel
durumundaydı ve öz-denetim/doğrulama kapısı `run_agent`'ı YENİDEN çağırdığı için her
düzeltici tur sıfırdan başlıyordu. Bütçeler toplanmıyor, çarpılıyordu.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.budget import BudgetStop, TurnBudget
from fusion_cli.core.events import ToolExecuted, ToolOutcome, TurnBudgetExhausted
from fusion_cli.core.tools import ToolContext
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


class _FakeClock:
    """Testin elle ilerlettiği saat. Gerçek bekleme yok."""

    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def now(self) -> float:
        return self.value


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


@pytest.fixture
def sink():
    return RecordingSink()


def _deps(tmp_path, sink, **config_args):
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _kur(monkeypatch, provider):
    def _build(spec, **kwargs):
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)
    return provider


def _budget(clock=None, **overrides) -> TurnBudget:
    limits = {
        "max_model_calls": 50,
        "max_verify_rounds": 2,
        "max_empty_retries": 2,
        "max_contract_repairs": 1,
        "max_auto_continues": 1,
        "max_idle_rounds": 3,
    }
    limits.update(overrides)
    return TurnBudget(clock=clock or _FakeClock(), **limits)


# --------------------------------------------------------------------------- #
# TurnBudget'in kendi davranışı
# --------------------------------------------------------------------------- #


def test_hak_biten_sayac_false_dondurur():
    budget = _budget(max_empty_retries=2)

    assert budget.take_empty_retry() is True
    assert budget.take_empty_retry() is True
    assert budget.take_empty_retry() is False
    assert budget.empty_retries == 2


def test_ilerleme_bosta_tur_sayacini_sifirlar():
    budget = _budget(max_idle_rounds=3)

    budget.record_round(progressed=False)
    budget.record_round(progressed=False)
    assert budget.idle_rounds == 2
    assert not budget.idle

    budget.record_round(progressed=True)
    assert budget.idle_rounds == 0


def test_ardisik_ilerlemesiz_turlar_bosta_esigine_ulasir():
    budget = _budget(max_idle_rounds=3)

    for _ in range(3):
        budget.record_round(progressed=False)

    assert budget.idle


def test_mutasyon_okuma_imzasini_tazeler_yazma_imzasini_tazelemez():
    budget = _budget()
    okuma_once = budget.signature("read_file", '{"path":"a"}', mutating=False)
    yazma_once = budget.signature("write_file", '{"path":"a"}', mutating=True)

    budget.record_mutation()

    # Çalışma alanı değişti: aynı dosyayı yeniden okumak yeni bilgi getirir.
    assert budget.signature("read_file", '{"path":"a"}', mutating=False) != okuma_once
    # Aynı yazmayı ikinci kez istemek her durumda tekrardır.
    assert budget.signature("write_file", '{"path":"a"}', mutating=True) == yazma_once


def test_ilk_durdurma_sebebi_korunur():
    budget = _budget()

    budget.halt(BudgetStop.NO_PROGRESS)
    budget.halt(BudgetStop.DEADLINE)

    assert budget.stop is BudgetStop.NO_PROGRESS


def test_sure_sinirsizken_zaman_asimi_olmaz():
    budget = _budget()
    assert budget.remaining_s() is None
    assert budget.out_of_time() is False


def test_sure_dolunca_zaman_asimi_bildirilir():
    clock = _FakeClock()
    budget = _budget(clock=clock)
    budget.total_timeout_s = 10.0

    clock.value = 9.0
    assert budget.out_of_time() is False

    clock.value = 10.5
    assert budget.out_of_time() is True


# --------------------------------------------------------------------------- #
# Döngü kapıları
# --------------------------------------------------------------------------- #


async def test_ayni_cagri_api_saglayicisinda_da_durdurulur(monkeypatch, tmp_path, sink):
    """Tekrar kapısı eskiden YALNIZCA web modellerinde açıktı.

    API modelleri aynı aracı aynı argümanlarla sınırsız tekrar edebiliyordu; kullanıcının
    gördüğü "aynı şeyi tekrar tekrar deniyor" davranışının bir kaynağı buydu.
    """
    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=[tool_call("list_dir", path=".")]) for _ in range(10)]
        ),
    )

    sonuc = await run_agent(
        "dur durak bilmez", _deps(tmp_path, sink, runtime={"agent_max_idle_rounds": 3})
    )

    assert not sonuc.ok
    engellenen = [
        event
        for event in sink.events
        if isinstance(event, ToolExecuted) and event.outcome is ToolOutcome.BLOCKED
    ]
    assert engellenen, "tekrar eden çağrı engellenmiş olmalı"
    # Tur ilk tekrarda ÖLMEZ; model kendini toparlayamayınca ilerleme-yok kapısı
    # bitirir. Böylece o ana kadar yapılmış iş korunur.
    tukendi = [event for event in sink.events if isinstance(event, TurnBudgetExhausted)]
    assert tukendi and tukendi[-1].reason == BudgetStop.NO_PROGRESS.value


async def test_ilerlemesiz_turlar_turu_bitirir_ve_sebebi_yayinlanir(
    monkeypatch, tmp_path, sink
):
    """Başarısız araç zinciri sonsuza kadar sürmez ve sessizce bitmez."""
    # Her tur FARKLI ve var olmayan bir yol okunur: çağrılar tekrar etmediği için
    # tekrar kapısı devreye girmez, ama hiçbir tur ilerleme üretmez.
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path=f"yok-{index}.txt")])
                for index in range(20)
            ]
        ),
    )

    sonuc = await run_agent(
        "olmayan dosyaları oku",
        _deps(tmp_path, sink, runtime={"agent_max_idle_rounds": 3}),
    )

    assert not sonuc.ok
    tukendi = [event for event in sink.events if isinstance(event, TurnBudgetExhausted)]
    assert tukendi, "tur neden bittiği kullanıcıya bildirilmeli"
    assert tukendi[-1].reason == BudgetStop.NO_PROGRESS.value
    assert tukendi[-1].idle_rounds >= 3


#: Otomatik-devam sezgiseli kısa/teslimsiz cevapları "yarım" sayar ve fazladan çağrı
#: açar. Bütçe testleri o davranışı değil, sayaçların paylaşımını ölçer.
TAM_CEVAP = "Görevi tamamladım; değişiklik `src/app.py:12` satırında yapıldı ve doğrulandı."


async def test_ozdenetim_turu_ana_turun_butcesini_devralir(monkeypatch, tmp_path, sink):
    """Faz 1'in çekirdek regresyonu: düzeltici tur bütçeyi baştan başlatmamalı.

    Öz-denetim `run_agent`'ı YENİDEN çağırır. Bütçe orada kurulsaydı ana turda
    harcanan model çağrıları unutulur ve toplam sınırı aşardı — bu, kullanıcının
    "bir türlü bitmeyen tur" olarak gördüğü davranıştı.

    Kurgu: ana tur TEMİZ biter (iki model çağrısı), sonra denetçi bir sorun bulur ve
    düzeltici tur açılır. Paylaşılan bütçede düzeltici tura yalnızca KALAN hak kadar
    çağrı düşer.
    """
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                # Ana tur: bir araç çağrısı, sonra tamamlanmış görünen nihai cevap.
                model_result(tool_calls=[tool_call("list_dir", path="alt-0")]),
                model_result(TAM_CEVAP),
                # Düzeltici tur: bütçe izin verdiği sürece araç çağırmayı sürdürür.
                *[
                    model_result(tool_calls=[tool_call("list_dir", path=f"duzelt-{i}")])
                    for i in range(20)
                ],
            ]
        ),
    )

    # Denetçi bir kez sorun bildirir; düzeltici tur `self_review=False` ile açıldığı
    # için tekrar çağrılmaz.
    async def _bulgu_var(*args, **kwargs):
        return "Bir sorun var, düzelt."

    monkeypatch.setattr(agent_loop.review, "review_turn", _bulgu_var)

    deps = _deps(tmp_path, sink, runtime={"agent_max_steps": 4, "self_review": True})
    await run_agent("uzun iş", deps)

    # Ana tur 2 çağrı harcadı; düzeltici tura yalnızca 2 hak kalmalı.
    assert provider.calls == 4, f"tur bütçesi paylaşılmadı: {provider.calls} çağrı"
    assert deps.budget.model_calls == 4
    assert deps.budget.stop is BudgetStop.MODEL_CALLS


async def test_butce_disaridan_verilebilir_ve_paylasilir(monkeypatch, tmp_path, sink):
    """Bütçe enjekte edilebilir: testler ve çağıranlar sınırı daraltabilir."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=[tool_call("list_dir", path=f"alt-{i}")]) for i in range(20)]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.budget = _budget(max_model_calls=2)

    sonuc = await run_agent("kısa bütçe", deps)

    assert deps.budget.model_calls == 2
    assert deps.budget.stop is BudgetStop.MODEL_CALLS
    assert not sonuc.ok


# --- Yürütme politikası da devredilir ----------------------------------------- #
#
# Ölçüldü: öz-denetim/doğrulama turu politikayı DÜZELTME METNİNDEN yeniden
# türetiyordu. Asıl görev BUGFIX (12 araç turu) olsa bile düzeltme metni basit
# sohbet sanılıp 5 tura düşüyor ve iş yarıda kesiliyordu.


async def test_yurutme_politikasi_ic_ice_turlarda_korunur(monkeypatch, tmp_path, sink):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    deps = _deps(tmp_path, sink)
    deps.execution = ExecutionPolicy(is_web=True, max_tool_rounds=12, max_model_calls=16)

    await run_agent("herhangi bir görev", deps)

    # Politika turun başında verildiyse `policy_for` ile EZİLMEMELİ.
    assert deps.execution.max_tool_rounds == 12
    assert deps.execution.max_model_calls == 16


async def test_politika_ilk_turda_bir_kez_belirlenir(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    deps = _deps(tmp_path, sink)
    assert deps.execution is None

    await run_agent("envanter.py'deki hataları düzelt", deps)

    assert deps.execution is not None
    # BUGFIX görevi cömert bütçe almalı; basit sohbet bütçesi değil.
    assert (deps.execution.max_tool_rounds or 99) > 5


# --- Duyurup hiçbir şey yapmadan durma ---------------------------------------- #
#
# Ölçüldü (Gemini web, aynı görev üç kez): iki koşuda model dosyaları okudu, sonra
# araç çağrısı ÜRETMEDEN düzyazı yazdı ("…aracını çağırıyorum" / kodu markdown
# bloğu olarak dökme). Fusion ikisini de nihai cevap sayıp turu bitirdi ve hiçbir
# dosya değişmedi. Kanıt kapısı yakalayamıyordu: `required_effect` dar metin
# kalıplarına bakar, "testleri geçir" ifadesinde boş kalır.


async def test_okuyup_duran_tur_bir_kez_devam_ettirilir(monkeypatch, tmp_path, sink):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.py")]),
                # Araç çağrısı YOK — yalnızca niyet beyanı.
                model_result("İlgili dosyaları düzenlemek için aracı çağırıyorum."),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.execution = ExecutionPolicy(
        is_web=True, complex_task=True, heuristic_auto_continue=False
    )

    await run_agent("testleri geçir", deps)

    # Tur duyuruda BİTMEMELİ: model bir şans daha almalı.
    assert provider.calls == 3, f"okuyup duran tur devam ettirilmedi: {provider.calls}"


async def test_degisiklik_yapilmis_turda_fazladan_devam_acilmaz(monkeypatch, tmp_path, sink):
    """Mutasyon olduysa düzyazı gerçek bir teslim olabilir; hak boşa harcanmaz."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="y.py", content="x = 1\n")]),
                model_result(TAM_CEVAP),
                model_result("fazladan"),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.execution = ExecutionPolicy(
        is_web=True, complex_task=True, heuristic_auto_continue=False
    )

    await run_agent("testleri geçir", deps)

    assert provider.calls == 2, f"gereksiz devam açıldı: {provider.calls}"


async def test_basit_gorevde_okuyup_durmak_devam_acmaz(monkeypatch, tmp_path, sink):
    """Salt-okuma bir soru için düzyazı ZATEN doğru cevaptır."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.py")]),
                model_result("Dosyada tek bir atama var."),
                model_result("fazladan"),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    # Gerçek web politikasıyla aynı: eski "yarım mı" sezgiseli web'de kapalıdır.
    deps.execution = ExecutionPolicy(
        is_web=True, complex_task=False, heuristic_auto_continue=False
    )

    await run_agent("bu dosyada ne var", deps)

    assert provider.calls == 2, f"basit görevde devam açıldı: {provider.calls}"


# --- Taklit kipte var olan dosya toptan yazılamaz ------------------------------ #
#
# Ölçüldü (Gemini web, aynı görev altı koşu): yıkıcı başarısızlıkların HEPSİNDE
# write_file vardı — bozuk sözdizimi, 13 ruff hatası, toplanamayan test dosyası.
# Yalnızca edit_file kullanan koşular eksik kalabildi ama kodu hiç bozmadı.


async def test_web_modelinde_var_olan_dosya_write_file_ile_ezilemez(monkeypatch, tmp_path, sink):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    hedef = tmp_path / "a.py"
    hedef.write_text("değerli = 1\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.py", content="yeni\n")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.execution = ExecutionPolicy(is_web=True, heuristic_auto_continue=False)

    await run_agent("a.py'yi düzelt", deps)

    assert hedef.read_text(encoding="utf-8") == "değerli = 1\n", "dosya ezilmemeli"
    engellenen = [
        event
        for event in sink.events
        if isinstance(event, ToolExecuted) and event.outcome is not ToolOutcome.OK
    ]
    assert engellenen and "edit_file" in engellenen[0].output


async def test_web_modelinde_yeni_dosya_yazilabilir(monkeypatch, tmp_path, sink):
    """Kısıt yalnızca ÜZERİNE yazmaya karşıdır; yeni dosya serbesttir."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="y.py", content="x = 1\n")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.execution = ExecutionPolicy(is_web=True, heuristic_auto_continue=False)

    await run_agent("y.py oluştur", deps)

    assert (tmp_path / "y.py").read_text(encoding="utf-8") == "x = 1\n"


async def test_api_modelinde_kisit_yok(monkeypatch, tmp_path, sink):
    """Ölçüm web modellerinde yapıldı; API modellerine kanıtsız kısıt konmaz.

    "Tam okunmamış dosyayı ezme" muhafızı ayrı bir konudur ve HER sağlayıcıda
    geçerlidir; bu yüzden model önce dosyayı okur.
    """
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    hedef = tmp_path / "a.py"
    hedef.write_text("eski\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.py")]),
                model_result(tool_calls=[tool_call("write_file", path="a.py", content="yeni\n")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.execution = ExecutionPolicy(is_web=False)

    await run_agent("a.py'yi yenile", deps)

    assert hedef.read_text(encoding="utf-8") == "yeni\n"
