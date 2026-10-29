"""Ajan döngüsü — Dalga 2 bulguları (A1/A2/A3 P1 kümesi).

Her test, 29 Ekim triyajında kodda ÖLÇÜLEN bir kusuru sabitler.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
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

TAM_CEVAP = "Tamamlandı: dosya yazıldı ve kontrol edildi, her şey çalışıyor."


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
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    return provider


# --- A2-01: son düzeltmeden sonra yeniden doğrulama ----------------------- #


class _SiraliDogrulayici:
    """Verilen sırayla sonuç döner; kaç kez çağrıldığını sayar."""

    def __init__(self, *sonuclar: bool) -> None:
        self._sonuclar = list(sonuclar)
        self.cagri = 0

    async def verify(self):
        ok = self._sonuclar[min(self.cagri, len(self._sonuclar) - 1)]
        self.cagri += 1
        return VerificationResult(
            ok=ok, summary="tamam" if ok else "bozuk", findings=() if ok else ("hata var",)
        )


async def test_son_duzeltme_dogrulanir_ve_basariliysa_tur_ok(monkeypatch, tmp_path, sink):
    """Ölçüldü (29 Ekim): iki başarısız doğrulama + işe yarayan ikinci düzeltme
    turu eskiden bayat `verification` yüzünden `ok=False` bitiyordu."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="1")]),
                model_result(TAM_CEVAP),
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="2")]),
                model_result(TAM_CEVAP),
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="3")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.verifier = _SiraliDogrulayici(False, False, True)

    sonuc = await run_agent("a.txt yaz", deps)

    assert deps.verifier.cagri == 3
    assert sonuc.ok


# --- A2-02: boş yanıt hakkı bitince başarı bildirilmez ---------------------- #


async def test_bos_yanit_hakki_bitince_tur_basarisiz_ve_aciklamali(monkeypatch, tmp_path, sink):
    """Ölçüldü (29 Ekim): boş yanıt hakkı bitince `_outcome(...)` varsayılanı
    `ok=True`, `budget_stopped=False` ve boş metinle bitiyordu."""
    _kur(monkeypatch, ScriptedProvider([model_result("")] * 6))
    deps = _deps(tmp_path, sink)

    sonuc = await run_agent("bir şey yap", deps)

    assert not sonuc.ok
    assert sonuc.budget_stopped
    assert sonuc.stop_reason == "empty_responses"
    assert sonuc.final_text.strip()


# --- A2-03: boş / sözleşme hatalı yanıt geri çekilmeyle AYNEN gönderilmez --- #


async def test_bos_yanit_ustel_geri_cekilmeye_girmez(monkeypatch, tmp_path, sink):
    """Ölçüldü (29 Ekim): `ok` ama boş yanıt `retryable` sayılıp yansıtıcı not
    eklenmeden `model_retry_attempts` kez aynen yeniden gönderiliyordu."""
    beklemeler: list[float] = []

    async def _sahte_bekle(delay_s: float) -> None:
        beklemeler.append(delay_s)

    monkeypatch.setattr(agent_loop, "_retry_sleep", _sahte_bekle)
    _kur(monkeypatch, ScriptedProvider([model_result(""), model_result(TAM_CEVAP)]))

    sonuc = await run_agent(
        "bir şey yap", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3})
    )

    assert beklemeler == []
    assert any("boş" in m.content.lower() for m in sonuc.messages if m.role == "user")


async def test_sozlesme_hatali_yanit_ustel_geri_cekilmeye_girmez(monkeypatch, tmp_path, sink):
    beklemeler: list[float] = []

    async def _sahte_bekle(delay_s: float) -> None:
        beklemeler.append(delay_s)

    monkeypatch.setattr(agent_loop, "_retry_sleep", _sahte_bekle)
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result("", ok=False, error="TOOL_CALL_INVALID: bozuk argüman"),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent(
        "bir şey yap", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3})
    )

    assert beklemeler == []
    assert sonuc.ok


# --- A2-04: sözleşme hatasıyla düşen çağrı "yapılmış" sayılmaz -------------- #


async def test_once_oku_hatasindan_sonra_ayni_yazma_tekrar_kapisina_takilmaz(
    monkeypatch, tmp_path, sink
):
    """Ölçüldü (29 Ekim): web modeli var olan küçük dosyaya `write_file` -> "önce
    oku" hatası -> okur -> AYNI `write_file` çağrısı `TOOL_CALL_DUPLICATE` ile
    engelleniyordu (imza hata anında sayılmış, unutulmamıştı)."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    (tmp_path / "a.txt").write_text("eski\n", encoding="utf-8")
    yaz = tool_call("write_file", path="a.txt", content="yeni\n")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[yaz]),
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(tool_calls=[yaz]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.execution = ExecutionPolicy(is_web=True, max_tool_rounds=12, max_model_calls=16)

    await run_agent("a.txt dosyasını değiştir", deps)

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "yeni\n"


# --- A1-18: web öğretmenine sır dosyası / kök dışı görsel gitmez ------------ #


@pytest.mark.parametrize(
    "ad",
    [
        "id_rsa",
        "deploy.pem",
        "credentials.json",
        "secrets.enc",
        ".npmrc",
        "terraform.tfstate",
        "prod.tfvars",
        ".env.local",
        "service-account.json",
    ],
)
def test_ogretmen_kesitine_sir_dosyasi_girmez(tmp_path, ad):
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    sir = tmp_path / ad
    sir.write_text("GIZLI_ICERIK_xyz", encoding="utf-8")
    kod = tmp_path / "app.py"
    kod.write_text("print('merhaba')\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.update({sir, kod})

    kesitler = _teacher_excerpts(context)

    assert [yol for yol, _ in kesitler] == ["app.py"]
    assert "GIZLI_ICERIK_xyz" not in repr(kesitler)


def test_ogretmen_kesiti_kaynak_kod_adlarini_sir_saymaz(tmp_path):
    """`token.py` / `reset-password.tsx` kaynak koddur; yanlış pozitif olmamalı."""
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    dosyalar = [tmp_path / "token.py", tmp_path / "reset-password.tsx"]
    for dosya in dosyalar:
        dosya.write_text("x = 1\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.update(dosyalar)

    assert len(_teacher_excerpts(context)) == 2


def test_ogretmen_kesiti_kok_disindaki_dosyayi_gondermez(tmp_path):
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    proje = tmp_path / "proje"
    proje.mkdir()
    disarida = tmp_path / "notlar.txt"
    disarida.write_text("özel not", encoding="utf-8")
    context = ToolContext(root=proje)
    context.touched.add(disarida)

    assert _teacher_excerpts(context) == []


def test_ogretmen_kesiti_buyuk_dosyayi_kirpar(tmp_path):
    from fusion_cli.engines.agent.engine_tools import _TEACHER_EXCERPT_CHARS, _teacher_excerpts

    buyuk = tmp_path / "big.py"
    buyuk.write_text("a" * (_TEACHER_EXCERPT_CHARS * 3), encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(buyuk)

    ((_, icerik),) = _teacher_excerpts(context)

    assert len(icerik) <= _TEACHER_EXCERPT_CHARS


def test_ogretmen_gorseli_kok_disindan_alinmaz(tmp_path):
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent.engine_tools import _teacher_images

    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "ekran.png").write_bytes(b"\x89PNG")
    disarida = tmp_path / "ozel.png"
    disarida.write_bytes(b"\x89PNG")
    # Varsayılan yapılandırma (`restrict_to_root=False`) kök dışına izin verir.
    context = ToolContext(root=proje, restrict_to_root=False)

    assert isinstance(_teacher_images([str(disarida)], context), ToolResult)
    assert isinstance(_teacher_images(["../ozel.png"], context), ToolResult)
    icerde = _teacher_images(["ekran.png"], context)
    assert isinstance(icerde, tuple) and len(icerde) == 1


# --- A1-06: dosya yazma izni yola bağlanır, proje dışı auto'da sorulur ------- #


def _yazma_araci(ad="write_file"):
    from fusion_cli.core.tools import Tool, ToolEffect

    return Tool(
        name=ad,
        description="",
        parameters={},
        run=lambda a, c: None,
        mutating=True,
        effect=ToolEffect.LOCAL,
    )


class _Sayac:
    """Kaç kez soruldu; verilen cevapları sırayla döner."""

    def __init__(self, *cevaplar):
        self.cevaplar = list(cevaplar)
        self.sorulan: list[str] = []

    async def confirm(self, request):
        self.sorulan.append(str(request.args.get("path")))
        return self.cevaplar.pop(0)


async def test_auto_modda_proje_disina_yazma_sorulur_proje_ici_sorulmaz(tmp_path):
    from fusion_cli.engines.agent.approval import (
        ApprovalAnswer,
        ApprovalMode,
        Decision,
        build_policy,
        build_request,
    )

    sayac = _Sayac(ApprovalAnswer.DENY)
    politika = build_policy(ApprovalMode.AUTO, sayac)
    proje = tmp_path / "proje"
    proje.mkdir()

    ici = build_request(_yazma_araci(), {"path": "src/a.py"}, root=proje)
    disi = build_request(_yazma_araci(), {"path": str(tmp_path / ".zshrc")}, root=proje)

    assert await politika.decide(ici) is Decision.ALLOW
    assert sayac.sorulan == []
    assert await politika.decide(disi) is Decision.DENIED
    assert len(sayac.sorulan) == 1
    assert "proje dışına" in (disi.risk or "")


async def test_oturum_izni_proje_disi_baska_yola_gecmez(tmp_path):
    from fusion_cli.engines.agent.approval import (
        ApprovalAnswer,
        ApprovalMemory,
        ApprovalMode,
        Decision,
        build_policy,
        build_request,
    )

    sayac = _Sayac(ApprovalAnswer.SESSION, ApprovalAnswer.DENY)
    politika = build_policy(ApprovalMode.AUTO, sayac, ApprovalMemory())
    proje = tmp_path / "proje"
    proje.mkdir()
    diger = tmp_path / "diger"
    diger.mkdir()

    ilk = build_request(_yazma_araci(), {"path": str(diger / "a.txt")}, root=proje)
    ayni_dizin = build_request(_yazma_araci(), {"path": str(diger / "b.txt")}, root=proje)
    baska_dizin = build_request(_yazma_araci(), {"path": str(tmp_path / ".zshrc")}, root=proje)

    assert await politika.decide(ilk) is Decision.ALLOW  # "oturum boyunca"
    assert await politika.decide(ayni_dizin) is Decision.ALLOW  # aynı dizin: sorulmaz
    assert len(sayac.sorulan) == 1
    assert await politika.decide(baska_dizin) is Decision.DENIED  # başka dizin: sorulur
    assert len(sayac.sorulan) == 2


async def test_manuel_kipte_proje_ici_oturum_izni_proje_disini_kapsamaz(tmp_path):
    from fusion_cli.engines.agent.approval import (
        ApprovalAnswer,
        ApprovalMemory,
        ApprovalMode,
        Decision,
        build_policy,
        build_request,
    )

    sayac = _Sayac(ApprovalAnswer.SESSION, ApprovalAnswer.DENY)
    politika = build_policy(ApprovalMode.SECURITY, sayac, ApprovalMemory())
    proje = tmp_path / "proje"
    proje.mkdir()

    ici = build_request(_yazma_araci(), {"path": "a.py"}, root=proje)
    ici_2 = build_request(_yazma_araci(), {"path": "b.py"}, root=proje)
    disi = build_request(_yazma_araci(), {"path": str(tmp_path / ".zshrc")}, root=proje)

    assert await politika.decide(ici) is Decision.ALLOW
    assert await politika.decide(ici_2) is Decision.ALLOW
    assert await politika.decide(disi) is Decision.DENIED
    assert len(sayac.sorulan) == 2


# --- A1-01: paralel araç sonuçlarının hepsi korunur -------------------------- #


def _tur(kimlikler, boyut=5_000):
    from fusion_cli.core.types import Message, ToolCall

    cagri = Message(
        "assistant", "", tool_calls=tuple(ToolCall(k, "read_file", "{}") for k in kimlikler)
    )
    sonuclar = [
        Message("tool", f"{k}:" + "x" * boyut, tool_call_id=k, name="read_file") for k in kimlikler
    ]
    return [cagri, *sonuclar]


def test_paralel_arac_sonuclarinin_hepsi_son_tur_olarak_korunur():
    """Ölçüldü (29 Ekim): yalnız SON tek `tool` mesajı korunuyordu; paralel 3 okumanın
    ilk 2 sonucu model onları görmeden 'temizlendi' notuna çevriliyordu."""
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.history import CLEARED_TOOL_OUTPUT, clear_old_tool_outputs

    mesajlar = [Message("system", "s"), Message("user", "görev")]
    mesajlar += _tur(["eski"])
    mesajlar += _tur(["a", "b", "c"])

    sonuc = clear_old_tool_outputs(mesajlar, threshold_chars=8_000)

    notu = CLEARED_TOOL_OUTPUT.format(chars=0).split("(")[0]
    icerik = {m.tool_call_id: m.content for m in sonuc if m.role == "tool"}
    assert notu in icerik["eski"]
    for kimlik in ("a", "b", "c"):
        assert icerik[kimlik].startswith(f"{kimlik}:xxxx"), f"{kimlik} sonucu temizlenmiş"


# --- A1-03 / A1-02: özet mesajı görev sanılmaz, iz özeti kesmez -------------- #

_DOLGU_METIN = "dolgu " * 200


def _uzun_oturum():
    from fusion_cli.core.types import Message

    mesajlar = [Message("system", "kimlik"), Message("user", "ilk görev")]
    for index in range(30):
        mesajlar += [Message("user", f"adım {index}"), Message("assistant", _DOLGU_METIN)]
    return mesajlar


async def test_turlar_arasi_ozet_harness_notu_olarak_eklenir(monkeypatch):
    """Ölçüldü (29 Ekim): `compress` özeti harness_note OLMADAN ekliyordu; 'devam et'
    deyince `task_effect` özet metnini 'en son gerçek görev' sanıyordu."""
    from fusion_cli.engines.agent import compaction

    async def ozetle(trace, config, publisher):
        return "Kullanıcı commit ve push istedi."

    monkeypatch.setattr(compaction, "_summarize", ozetle)

    sonuc = await compaction.compress(_uzun_oturum(), config=make_config(), threshold_chars=20_000)

    ozet = next(m for m in sonuc if m.content.startswith("[önceki konuşmanın özeti]"))
    assert ozet.harness_note


def test_devam_et_ozet_metnini_gorev_sanmaz():
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.action_evidence import task_effect

    gecmis = [
        Message("user", "README.md dosyasını güncelle"),
        Message("assistant", "tamam"),
        # Eski kayıtlarda özet harness_note OLMADAN saklanmış olabilir.
        Message(
            "user",
            "[önceki konuşmanın özeti]\nKullanıcı sonunda commit ve push yapılmasını istedi.",
        ),
    ]

    assert task_effect("devam et", gecmis) == task_effect("README.md dosyasını güncelle")
    assert task_effect("devam et", gecmis) != "git_push"


async def test_ardisik_tur_ici_sikistirmada_kurallar_kaybolmaz(monkeypatch):
    """Tur içi özet harness_note olduğundan kural bloğu ikinci sıkıştırmada düşüyordu."""
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import compaction

    async def ozetle(trace, config, publisher):
        return "özet"

    monkeypatch.setattr(compaction, "_summarize", ozetle)
    mesajlar = [Message("system", "kimlik"), Message("user", "ilk görev")]
    for index in range(30):
        kural = " main dalına asla push etme" if index == 3 else ""
        mesajlar += [Message("user", f"adım {index}.{kural}"), Message("assistant", _DOLGU_METIN)]

    ilk = await compaction.compact_in_turn(mesajlar, config=make_config(), threshold_chars=20_000)
    for index in range(30):
        ilk += [Message("user", f"yeni {index}"), Message("assistant", _DOLGU_METIN)]
    ikinci = await compaction.compact_in_turn(ilk, config=make_config(), threshold_chars=20_000)

    assert "main dalına asla push etme" in "\n".join(m.content for m in ikinci)


def test_iz_onceki_ozet_mesajini_kesmez():
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import history

    uzun_ozet = "[önceki konuşmanın özeti]\n" + "ÖNEMLİ_AYRINTI " * 300
    iz = history.transcript([Message("user", uzun_ozet)], limit=60_000)

    assert iz.count("ÖNEMLİ_AYRINTI") == 300


def test_iz_arac_sonucunun_basini_ve_sonunu_hata_icin_daha_fazlasini_tutar():
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import history

    govde = "BAŞ" + "o" * 5_000 + "SON"
    basarili = history.transcript([Message("tool", govde, name="run_shell", ok=True)], limit=60_000)
    hata = history.transcript([Message("tool", govde, name="run_shell", ok=False)], limit=60_000)

    assert "BAŞ" in basarili and "SON" in basarili
    assert len(hata) > len(basarili)


def test_sikistirma_izinde_mesaj_payi_mesaj_sayisina_gore_olceklenir():
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import compaction

    az = [Message("user", "x")] * 10
    cok = [Message("user", "x")] * 400

    assert compaction.trace_message_chars(az) > compaction.trace_message_chars(cok)
    assert compaction.trace_message_chars(cok) >= 300


# --- A1-04: bağlam penceresi hatasından eşik öğrenilir ---------------------- #


def test_baglam_tasmasi_hatasi_taniniir_ve_pencere_hatadan_okunur():
    from fusion_cli.engines.agent.context_budget import (
        chars_for_window,
        is_context_overflow,
        learned_threshold_chars,
    )

    hata = "ContextWindowExceededError: maximum context length is 8192 tokens, you requested 12000"

    assert is_context_overflow(hata)
    assert not is_context_overflow("rate limit exceeded")
    ogrenilen = learned_threshold_chars(hata, history_chars=120_000)
    assert ogrenilen == max(4_000, chars_for_window(8_192))
    assert ogrenilen < 120_000


def test_pencere_hatada_yoksa_gecmisin_yarisi_alinir():
    from fusion_cli.engines.agent.context_budget import learned_threshold_chars

    assert learned_threshold_chars("prompt is too long", history_chars=100_000) == 50_000


def test_sistem_ve_arac_payi_olculen_sema_boyutunu_karsilar():
    """Ölçüldü (29 Ekim): 48 yerleşik araç şeması 17.221 karakter + ~10 bin karakter
    sistem istemi ≈ 9 bin token; eski 4.000 token payı bunun yarısından azdı."""
    import json

    from fusion_cli.engines.agent.context_budget import SYSTEM_AND_TOOLS_RESERVE_TOKENS
    from fusion_cli.tools import build_registry

    sema_token = len(json.dumps(build_registry().schemas(), ensure_ascii=False)) // 3
    assert sema_token + 3_000 <= SYSTEM_AND_TOOLS_RESERVE_TOKENS


async def test_baglam_tasmasi_esigi_kucultur_gecmisi_sikistirir_ve_yeniden_dener(
    monkeypatch, tmp_path, sink
):
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import compaction

    async def ozetle(trace, config, publisher):
        return "özet"

    monkeypatch.setattr(compaction, "_summarize", ozetle)
    gecmis = [Message("system", "kimlik"), Message("user", "ilk görev")]
    for index in range(30):
        gecmis += [Message("user", f"adım {index}"), Message("assistant", "d" * 2_000)]
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    "",
                    ok=False,
                    error="ContextWindowExceededError: maximum context length is 8192 tokens",
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)

    sonuc = await run_agent("devam et", deps, history=gecmis)

    assert sonuc.ok
    assert deps.learned_compression_chars is not None
    assert deps.learned_compression_chars < 100_000
    assert deps.condensations >= 1


# --- A1-42: belirsiz dış etki gözlemle kapanır, bilinmeyen kimlik çökertmez -- #


def _plan_kos(tmp_path, kimlik="eff"):
    from dataclasses import replace

    from fusion_cli.core.execution_plan import ExecutionPlan, StepStatus
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger, WorkflowBudget
    from tests.test_plan_repair import _deps as plan_deps
    from tests.test_plan_runner import _step

    adim = replace(_step("send"), attempts=1, status=StepStatus.RUNNING)
    butce = WorkflowBudget(planning=2, per_step=4, recovery=2, final=2)
    kos = _PlanRun(
        "iş",
        plan_deps(tmp_path),
        None,
        ExecutionPlan(kimlik, "iş", (adim,)),
        butce,
        BudgetLedger(butce),
    )
    return kos, adim


def _uzak_arac():
    from fusion_cli.core.tools import Tool, ToolEffect, ToolResult

    return Tool(
        "remote", "", {}, lambda *_: ToolResult(""), mutating=True, effect=ToolEffect.REMOTE_WRITE
    )


def _kapsam(*hedef):
    from fusion_cli.core.tools import AuthorizationScope

    return AuthorizationScope("server", "account", "write", hedef)


async def test_bilinmeyen_cagri_kimligi_finish_ile_cokertmez(tmp_path):
    from fusion_cli.engines.agent.effect_checkpoint import PlanEffectRecorder

    kos, _ = _plan_kos(tmp_path)

    await PlanEffectRecorder(kos, "send", 1).finish("yok", False)  # KeyError atmamalı


async def test_bilinmeyen_adim_acik_hata_verir(tmp_path):
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.effect_checkpoint import EffectAdmissionError, PlanEffectRecorder

    kos, _ = _plan_kos(tmp_path)
    arac = _uzak_arac()

    with pytest.raises(EffectAdmissionError):
        await PlanEffectRecorder(kos, "olmayan", 1).prepare(
            ToolCall("c", "remote", "{}"), arac, arac.effect, _kapsam("a")
        )


async def test_gozlemle_kapanan_belirsiz_etki_sonraki_yazmayi_kilitlemez(tmp_path):
    """Ölçüldü (29 Ekim): `finish(ok=False)` kaydı AMBIGUOUS yapıyor, kapatan geçiş
    yoktu; aynı kapsamdaki sonraki tüm yazmalar plan sonuna dek reddediliyordu."""
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.effect_checkpoint import (
        EffectAdmissionError,
        PlanEffectRecorder,
        settle_observed,
    )

    kos, _ = _plan_kos(tmp_path)
    kaydedici = PlanEffectRecorder(kos, "send", 1)
    arac = _uzak_arac()
    await kaydedici.prepare(ToolCall("ilk", "remote", "{}"), arac, arac.effect, _kapsam("a"))
    await kaydedici.finish("ilk", False)
    with pytest.raises(EffectAdmissionError):
        await kaydedici.prepare(ToolCall("ikinci", "remote", "{}"), arac, arac.effect, _kapsam("a"))

    assert settle_observed(kos, "send") is True

    await kaydedici.prepare(ToolCall("ikinci", "remote", "{}"), arac, arac.effect, _kapsam("a"))


async def test_kanitli_gozlem_dogrulamasi_belirsiz_etkiyi_kapatir(tmp_path, monkeypatch):
    from fusion_cli.core.effects import EffectPhase
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent import plan_runner
    from fusion_cli.engines.agent.effect_checkpoint import PlanEffectRecorder
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.step_verification import StepVerificationResult

    kos, adim = _plan_kos(tmp_path, "eff2")
    kaydedici = PlanEffectRecorder(kos, "send", 1)
    arac = _uzak_arac()
    await kaydedici.prepare(ToolCall("ilk", "remote", "{}"), arac, arac.effect, _kapsam("a"))
    await kaydedici.finish("ilk", False)

    async def kanitli(*args, **kwargs):
        return StepVerificationResult(ok=True, evidence=("salt-okunur makbuz",))

    monkeypatch.setattr(plan_runner, "verify_step", kanitli)
    sonuc = await kos.verify(adim, AgentOutcome(final_text="", messages=[]), observe=True)

    assert sonuc.ok
    assert {i.phase for i in kos.effect_intents.values()} == {EffectPhase.RESPONDED}


# --- A2-08: view_image açıklamasında nokta içeren belirteçler bozulmaz ------- #


def test_gorsel_aciklamasinda_dosya_adi_surum_ve_alan_adi_bozulmaz():
    from fusion_cli.engines.agent.image_view import collapse_repeats

    metin = "player.png bir ikon. Sürüm v1.2, oran 3.5. example.com logosu."

    sonuc = collapse_repeats(metin)

    assert "player.png" in sonuc
    assert "v1.2" in sonuc
    assert "3.5" in sonuc
    assert "example.com" in sonuc


def test_gorsel_aciklamasinda_tam_cumle_tekrari_hala_ayiklanir():
    from fusion_cli.engines.agent.image_view import collapse_repeats

    metin = "Bir logo. Oyunda kullanılabilir. Oyunda kullanılabilir. Oyunda kullanılabilir!"

    assert collapse_repeats(metin).count("Oyunda kullanılabilir") == 1


# --- A3-04 / A3-05: UTF-8 olmayan dosya doğrulayıcıyı/talimat okumayı çökertmez - #


def test_utf8_olmayan_talimat_dosyasi_turu_cokertmez(tmp_path):
    from fusion_cli.engines.agent.project_instructions import read_project_instructions

    (tmp_path / "CLAUDE.md").write_bytes("Kural: testleri calistir, ğüşiöç".encode("cp1254"))

    sonuc = read_project_instructions(tmp_path)  # UnicodeDecodeError atmamalı

    assert "Kural: testleri calistir" in sonuc


def test_utf8_olmayan_tema_dosyalari_dogrulayiciyi_cokertmez(tmp_path):
    from fusion_cli.engines.agent.php_verify import missing_theme_references, theme_root

    tema = tmp_path / "tema"
    tema.mkdir()
    (tema / "style.css").write_bytes("/* Theme Name: Çiçek Teması */".encode("cp1254"))
    sayfa = tema / "page.php"
    sayfa.write_bytes("<?php // şğüıö ?>".encode("cp1254"))

    assert theme_root(sayfa) == tema
    assert missing_theme_references(sayfa, tmp_path) == []


# --- A1-23: read_session olay döngüsünü bloklamaz, sınır dışı değer kıstırılır - #


async def test_read_session_kaynagi_olay_dongusu_disinda_okur(tmp_path, monkeypatch):
    """Ölçüldü (29 Ekim): `source.read` (disk G/Ç) async `_run` içinde EŞZAMANLI
    çağrılıyor, olay döngüsünü bloklıyordu."""
    import threading

    from fusion_cli.engines.agent.engine_tools import build_history_tool
    from fusion_cli.history import models

    okuyan: list[int] = []

    class _Kaynak:
        def read(self, session_id, *, cursor, limit):
            okuyan.append(threading.get_ident())
            return (models.Turn(role="user", text="merhaba"),)

    monkeypatch.setattr("fusion_cli.history.source_by_name", lambda home, name: _Kaynak())
    arac = build_history_tool(tmp_path)

    sonuc = await arac.run({"source": "x", "session_id": "s"}, ToolContext(root=tmp_path))

    assert sonuc.ok
    assert okuyan and okuyan[0] != threading.get_ident()


async def test_read_session_sinir_disi_limit_sessizce_varsayilana_donmez(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.engine_tools import _READ_SESSION_MAX_LIMIT, build_history_tool
    from fusion_cli.history import models

    istenen: list[int] = []

    class _Kaynak:
        def read(self, session_id, *, cursor, limit):
            istenen.append(limit)
            return tuple(models.Turn(role="user", text=f"m{i}") for i in range(limit))

    monkeypatch.setattr("fusion_cli.history.source_by_name", lambda home, name: _Kaynak())
    arac = build_history_tool(tmp_path)

    await arac.run({"source": "x", "session_id": "s", "limit": 500}, ToolContext(root=tmp_path))

    # Kıstırılmış üst sınır (+1: devam var mı bakışı); eskiden varsayılan 20 olurdu.
    assert istenen == [_READ_SESSION_MAX_LIMIT + 1]
