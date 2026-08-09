"""Agent döngüsü — araç çağrısı, onay, refleksiyon, otomatik devam, alt-ajan."""

from __future__ import annotations

import pytest

from fusion_cli.core.events import (
    ContextCompressed,
    SelfReviewFinished,
    SubAgentFinished,
    SubAgentStarted,
    ToolExecuted,
    ToolOutcome,
    TurnBudgetExhausted,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent import reflexion
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, _parse_arguments_checked, run_agent

from .fakes import (
    AlwaysApprove,
    AlwaysReject,
    RecordingSink,
    ScriptedAsker,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

#: Otomatik-devam sezgiseli kısa ve teslimsiz cevapları "yarım" sayar. Bu sabiti
#: kullanan testler o davranışı değil, sınadıkları asıl akışı ölçer.
TAM_CEVAP = "Görevi tamamladım; ilgili değişiklik `src/app.py:12` satırında yapıldı ve doğrulandı."


def _icerir(sonuc, metin):
    return any(mesaj.content == metin for mesaj in sonuc.messages)


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


@pytest.fixture
def sink():
    return RecordingSink()


def _deps(tmp_path, sink, *, mode=ApprovalMode.AUTO, prompter=None, asker=None, **config_args):
    prompter = prompter or AlwaysApprove()
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(mode, prompter),
        tool_context=ToolContext(root=tmp_path),
        asker=asker,
    )


def _kur(monkeypatch, provider):
    def _build(
        spec,
        *,
        publisher=None,
        retry_delays_s=(),
        channel=None,
        clock=None,
        sleeper=None,
        background=False,
        health=None,
        key_pools=None,
        web_sessions=None,
    ):
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)
    return provider


# --------------------------------------------------------------------------- #


async def test_araçsiz_yanit_dogrudan_dondurulur(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result("iste cevap")]))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink))

    assert sonuc.final_text == "iste cevap"
    assert sonuc.tool_calls_made == 0


async def test_arac_cagrisi_calisir_ve_sonuc_gecmise_eklenir(monkeypatch, tmp_path, sink):
    (tmp_path / "a.txt").write_text("dosya icerigi", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert sonuc.final_text == TAM_CEVAP
    assert sonuc.tool_calls_made == 1
    arac_mesaji = next(m for m in sonuc.messages if m.role == "tool")
    assert "dosya icerigi" in arac_mesaji.content
    assert arac_mesaji.name == "read_file"


async def test_arac_calistirmasi_olay_yayinlar(monkeypatch, tmp_path, sink):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("oku", _deps(tmp_path, sink))

    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.name == "read_file" and olay.outcome is ToolOutcome.OK


async def test_reddedilen_onay_hata_sayilmaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent(
        "yaz", _deps(tmp_path, sink, mode=ApprovalMode.SECURITY, prompter=AlwaysReject())
    )

    assert not (tmp_path / "a.txt").exists()
    arac_mesaji = next(m for m in sonuc.messages if m.role == "tool")
    assert "onaylanmadı" in arac_mesaji.content
    # Reddetme refleksiyon notu tetiklememeli.
    assert not _icerir(sonuc, reflexion.STANDARD_NOTE)
    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.outcome is ToolOutcome.DENIED


async def test_arac_hatasi_refleksiyon_notu_enjekte_eder(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="yok.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert _icerir(sonuc, reflexion.STANDARD_NOTE)


async def test_refleksiyon_kapatilabilir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="yok.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink, runtime={"reflexion": False}))

    assert not _icerir(sonuc, reflexion.STANDARD_NOTE)


async def test_yarim_kalan_is_bir_kez_devam_ettirilir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result("bak"),  # kisa, teslimsiz -> yarim gorunur
                model_result("iste tam cevap `kod` ile birlikte"),
            ]
        ),
    )

    sonuc = await run_agent("yap", _deps(tmp_path, sink))

    assert provider.calls == 3
    assert _icerir(sonuc, reflexion.AUTO_CONTINUE_NOTE)


async def test_otomatik_devam_en_fazla_bir_kez_calisir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result("kisa"),
                model_result("yine kisa"),
            ]
        ),
    )

    await run_agent("yap", _deps(tmp_path, sink))

    assert provider.calls == 3


async def test_adim_siniri_turu_sonlandirir(monkeypatch, tmp_path, sink):
    # Her tur FARKLI bir yol okunur: çağrılar tekrar etmediği için tekrar kapısı
    # devreye girmez ve turu gerçekten adım sınırı bitirir.
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=f"alt-{index}")])
                for index in range(20)
            ]
        ),
    )

    sonuc = await run_agent("sonsuz", _deps(tmp_path, sink, runtime={"agent_max_steps": 3}))

    assert sonuc.hit_step_limit
    assert any(isinstance(e, TurnBudgetExhausted) for e in sink.events)


async def test_model_hatasi_turu_bitirir(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result(ok=False, error="saglayici coktu")]))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink))

    assert sonuc.final_text == "saglayici coktu"


async def test_plan_modunda_degistirici_arac_calismaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("planla", _deps(tmp_path, sink, mode=ApprovalMode.PLAN), plan_mode=True)

    assert not (tmp_path / "a.txt").exists()


async def test_plan_modu_sistem_promptuna_eklenir(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("plan")]))

    await run_agent("planla", _deps(tmp_path, sink), plan_mode=True)

    sistem = provider.seen_messages[0][0]
    assert "PLAN MODUNDASIN" in sistem.content


async def test_alt_ajan_temiz_baglamla_calisir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("spawn_agent", task="alt gorev")]),
                model_result("alt ajan cevabi"),  # alt-ajanin turu
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("bol", _deps(tmp_path, sink))

    assert sonuc.final_text == TAM_CEVAP
    assert any(isinstance(e, SubAgentStarted) for e in sink.events)
    assert any(isinstance(e, SubAgentFinished) for e in sink.events)


async def test_alt_ajan_derinlik_siniri_asilmaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("spawn_agent", task="birinci")]),
                model_result(tool_calls=[tool_call("spawn_agent", task="ikinci")]),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("bol", _deps(tmp_path, sink))

    olaylar = [e for e in sink.events if isinstance(e, SubAgentStarted)]
    assert len(olaylar) == 1  # ikinci seviye reddedildi


async def test_ask_user_araci_yalnizca_asker_varken_sunulur(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    await run_agent("gorev", _deps(tmp_path, sink))
    araclarsiz = provider.calls

    assert araclarsiz == 1


async def test_ask_user_cevabi_modele_dondurulur(monkeypatch, tmp_path, sink):
    asker = ScriptedAsker("mavi olsun")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("ask_user", question="hangi renk?")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("renk sec", _deps(tmp_path, sink, asker=asker))

    assert asker.questions == ["hangi renk?"]
    assert any("mavi olsun" in m.content for m in sonuc.messages if m.role == "tool")


async def test_oz_denetim_sorun_yoksa_ikinci_tur_acmaz(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("temiz cevap")]))
    monkeypatch.setattr(agent_loop.review, "review_turn", _sabit_denetim(""))

    await run_agent("gorev", _deps(tmp_path, sink, runtime={"self_review": True}))

    assert provider.calls == 1
    olay = next(e for e in sink.events if isinstance(e, SelfReviewFinished))
    assert not olay.issue_found


async def test_oz_denetim_sorun_bulursa_duzeltici_tur_calisir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch, ScriptedProvider([model_result("eksik cevap"), model_result("duzeltilmis")])
    )
    monkeypatch.setattr(agent_loop.review, "review_turn", _sabit_denetim("testleri calistirmadin"))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink, runtime={"self_review": True}))

    assert provider.calls == 2
    assert sonuc.final_text == "duzeltilmis"


async def test_baglam_sikistirma_olayi_yayinlanir(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    async def _sikistir(messages, *, config, publisher=None):
        return messages[:1]

    monkeypatch.setattr(agent_loop.compaction, "compress", _sikistir)

    await run_agent("gorev", _deps(tmp_path, sink))

    assert any(isinstance(e, ContextCompressed) for e in sink.events)


# --- Argüman ayrıştırma ----------------------------------------------------- #


def test_bozuk_json_bos_sozluk_ve_hata_dondurur():
    arguments, hata = _parse_arguments_checked("{bozuk")
    assert arguments == {}
    assert hata is not None and "JSON" in hata


def test_sozluk_olmayan_json_bos_sozluk_ve_hata_dondurur():
    arguments, hata = _parse_arguments_checked("[1,2]")
    assert arguments == {}
    assert hata == "arguments bir JSON nesnesi olmalı"


def test_bos_arguman_bos_sozluk_ve_hata_dondurur():
    arguments, hata = _parse_arguments_checked("")
    assert arguments == {}
    assert hata is not None


def test_gecerli_json_hatasiz_ayristirilir():
    assert _parse_arguments_checked('{"path":"a.txt"}') == ({"path": "a.txt"}, None)


def _sabit_denetim(sonuc):
    async def _review(task, final_text, messages, *, config, publisher=None):
        return sonuc

    return _review


# --- Etkileşimsiz ortam ------------------------------------------------------ #


async def test_asker_yoksa_ask_user_araci_modele_sunulmaz(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    await run_agent("gorev", _deps(tmp_path, sink, asker=None))

    semalar = provider.seen_requests[0]
    assert "ask_user" not in {s["function"]["name"] for s in semalar}


async def test_asker_varsa_ask_user_araci_sunulur(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    await run_agent("gorev", _deps(tmp_path, sink, asker=ScriptedAsker()))

    semalar = provider.seen_requests[0]
    assert "ask_user" in {s["function"]["name"] for s in semalar}


async def test_plan_modunda_engelleme_reddetmeden_ayirt_edilir(monkeypatch, tmp_path, sink):
    """Plan modunda kimseye sorulmaz; model bunu "kullanıcı reddetti" sanmamalı."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("planla", _deps(tmp_path, sink, mode=ApprovalMode.PLAN), plan_mode=True)

    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.outcome is ToolOutcome.BLOCKED
    arac_mesaji = next(m for m in sonuc.messages if m.role == "tool")
    assert "PLAN MODU" in arac_mesaji.content


# --- Doğrulama kapısının geri besleme yolu ----------------------------------- #
#
# Bugüne kadar doğrulama sonucu YALNIZCA ders güvenini besliyordu; modele hiç
# ulaşmıyordu. Yani kapı kırılsa bile agent bunu öğrenmiyor, çıktı değişmiyordu.


class _SahteDogrulayici:
    """İstenen sonucu döndüren doğrulayıcı; kaç kez çağrıldığını sayar."""

    def __init__(self, sonuc):
        self._sonuc = sonuc
        self.calls = 0

    async def verify(self):
        self.calls += 1
        return self._sonuc


async def test_kapi_kirilirsa_bulgular_duzeltici_tura_gider(monkeypatch, tmp_path, sink):
    from fusion_cli.core.verification import VerificationResult

    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.html", content="<h1>x")]),
                model_result(TAM_CEVAP),
                model_result("duzeltildi"),
                # Kapı düzeltmeden sonra bir kez daha bakar; ikinci düzeltici tur da
                # betikte karşılığını bulmalı.
                model_result("duzeltildi"),
            ]
        ),
    )
    dogrulayici = _SahteDogrulayici(
        VerificationResult(ok=False, summary="2 sorun", findings=("boş bağlantı: 18 adet",))
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.verifier = dogrulayici

    sonuc = await run_agent("site yap", deps)

    assert dogrulayici.calls >= 1
    # Doğrulayıcı HER SEFERİNDE düşüyor: kapı hakkı bitince tur başarı sayılmaz
    # ve cevap uyarıyla açılır (bkz. `_mark_unverified`). Düzeltici turun metni
    # uyarının ardında korunur.
    assert sonuc.final_text.endswith("duzeltildi")
    assert "DOĞRULAMA GEÇMEDİ" in sonuc.final_text
    gonderilen = provider.seen_messages[-1]
    assert any("boş bağlantı: 18 adet" in mesaj.content for mesaj in gonderilen), (
        "somut bulgu modele ulaşmalı"
    )


async def test_kapi_gecerse_duzeltici_tur_acilmaz(monkeypatch, tmp_path, sink):
    from fusion_cli.core.verification import VerificationResult

    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.html", content="<h1>x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.verifier = _SahteDogrulayici(VerificationResult(ok=True))

    await run_agent("site yap", deps)

    assert provider.calls == 2


async def test_dogrulayici_yoksa_kapi_hic_calismaz(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    await run_agent("gorev", _deps(tmp_path, sink, runtime={"self_review": False}))

    assert provider.calls == 1


async def test_plan_modunda_kapi_calismaz(monkeypatch, tmp_path, sink):
    from fusion_cli.core.verification import VerificationResult

    _kur(monkeypatch, ScriptedProvider([model_result("plan")]))
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.verifier = _SahteDogrulayici(VerificationResult(ok=False, findings=("sorun",)))

    await run_agent("gorev", deps, plan_mode=True)

    assert deps.verifier.calls == 0


async def test_sistem_promptu_beceri_kutuphanesini_duyurur(monkeypatch, tmp_path, sink):
    """Model 126 skill'lik kütüphanenin varlığından haberdar olmalı.

    Gerçek koşuda find_skill hiç çağrılmadı; araç kayıtlıydı ama sistem promptunda
    "skill" kelimesi hiç geçmiyordu. Kullanılmayan yetenek, olmayan yetenektir.
    """
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    await run_agent("arayüz yap", _deps(tmp_path, sink, runtime={"self_review": False}))

    sistem = provider.seen_messages[0][0]
    assert sistem.role == "system"
    assert "find_skill" in sistem.content


async def test_duzeltici_turdan_sonra_kapi_bir_kez_daha_calisir(monkeypatch, tmp_path, sink):
    """Düzeltici turun KENDİ kırdığı şey yakalanmalı.

    Gerçek hata: düzeltici tur index.html'i yeniden yazarken <script> etiketini
    düşürdü; sayfa boş kaldı ve kapı bir daha bakmadığı için bu hâliyle teslim edildi.
    """
    from fusion_cli.core.verification import VerificationResult

    sonuclar = [
        VerificationResult(ok=False, summary="ilk", findings=("boş bağlantı",)),
        VerificationResult(ok=False, summary="ikinci", findings=("script etiketi düştü",)),
        VerificationResult(ok=True),
    ]

    class _Kademeli:
        def __init__(self):
            self.calls = 0

        async def verify(self):
            self.calls += 1
            return sonuclar[min(self.calls - 1, len(sonuclar) - 1)]

    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.html", content="<h1>")]),
                model_result(TAM_CEVAP),
                model_result("ilk duzeltme"),
                model_result("ikinci duzeltme"),
            ]
        ),
    )
    dogrulayici = _Kademeli()
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.verifier = dogrulayici

    sonuc = await run_agent("site yap", deps)

    assert dogrulayici.calls == 2, "kapı düzeltmeden sonra bir kez daha bakmalı"
    # İkinci bakış da düştüğü için tur başarı sayılmaz; düzeltici turun metni
    # uyarının ardında korunur (bkz. `_mark_unverified`).
    assert sonuc.final_text.endswith("ikinci duzeltme")
    assert sonuc.ok is False
    assert provider.calls == 4


async def test_kapi_bulgusuz_basarisizlikta_da_duzeltir(monkeypatch, tmp_path, sink):
    """`ok=False` ama `findings` boşsa da düzeltici tur AÇILMALI.

    Gerçek hata: koşul `not verification.findings` görünce döngüyü kırıyordu.
    Bulgu üretmeyen bir doğrulayıcı (ör. yalnızca özet dolduran bir komut kapısı)
    başarısız olduğunda agent düzeltmeye hiç başlamıyor, kapı yalnızca ders
    güvenini etkileyip sessizce işlevsiz kalıyordu.
    """
    from fusion_cli.core.verification import VerificationResult

    sonuclar = [
        VerificationResult(ok=False, summary="komut başarısız (çıkış 1): pytest"),
        VerificationResult(ok=True),
    ]

    class _BulgusuzKapi:
        def __init__(self):
            self.calls = 0

        async def verify(self):
            self.calls += 1
            return sonuclar[min(self.calls - 1, len(sonuclar) - 1)]

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.py", content="x")]),
                model_result(TAM_CEVAP),
                model_result("duzeltme yapildi"),
            ]
        ),
    )
    dogrulayici = _BulgusuzKapi()
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.verifier = dogrulayici

    sonuc = await run_agent("test yaz", deps)

    assert dogrulayici.calls == 2, "kapı düzeltmeden sonra bir kez daha bakmalı"
    assert sonuc.final_text == "duzeltme yapildi"


async def test_kapi_sonsuz_dongu_yapmaz(monkeypatch, tmp_path, sink):
    """Kapı hep kırık kalsa bile tur sınırlı sayıda düzeltme denemesiyle biter."""
    from fusion_cli.core.verification import VerificationResult

    class _HepKirik:
        def __init__(self):
            self.calls = 0

        async def verify(self):
            self.calls += 1
            return VerificationResult(ok=False, summary="x", findings=("sorun",))

    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=[tool_call("write_file", path="a.html", content="x")])]
            + [model_result(TAM_CEVAP) for _ in range(10)]
        ),
    )
    dogrulayici = _HepKirik()
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.verifier = dogrulayici

    await run_agent("site yap", deps)

    assert dogrulayici.calls <= 2, f"kapı {dogrulayici.calls} kez çalıştı — sınır aşıldı"


async def test_oz_denetim_duzeltmesi_ic_ice_kapi_turu_acmaz(monkeypatch, tmp_path, sink):
    """Öz-denetimin düzeltici turu KENDİ kapı turlarını çalıştırmamalı.

    Gerçek hata: bu tur `verify=False` almıyordu, dolayısıyla kendi içinde iki kapı
    turu daha açıyordu. Üst sınır 2 konmuşken toplam 4 tura çıkıyor, maliyet sessizce
    ikiye katlanıyordu.
    """
    from fusion_cli.core.verification import VerificationResult

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.html", content="<h1>x")]),
                model_result(TAM_CEVAP),
                model_result("oz denetim duzeltmesi"),
                model_result("kapi duzeltmesi"),
                model_result("kapi duzeltmesi 2"),
            ]
        ),
    )
    monkeypatch.setattr(agent_loop.review, "review_turn", _sabit_denetim("bir sorun var"))
    dogrulayici = _SahteDogrulayici(VerificationResult(ok=False, findings=("sorun",)))
    deps = _deps(tmp_path, sink, runtime={"self_review": True})
    deps.verifier = dogrulayici

    await run_agent("site yap", deps)

    assert dogrulayici.calls <= 2, f"kapı {dogrulayici.calls} kez çalıştı; iç içe doğrulama var"


async def test_bos_cevapta_bir_kez_daha_denenir(monkeypatch, tmp_path, sink):
    """Model boş cevap verirse tur HİÇBİR İŞ YAPMADAN bitmemeli.

    Ölçüldü (transkript): model `ok=true` ama metinsiz ve araçsız cevap
    dönebiliyor. Tek modelli zincirde yedek yoktur (hedged kısa devre yapar), o
    yüzden çare yeniden denemektir. Sınırlıdır: boş cevap ısrar ederse tur biter,
    sonsuz döngü yok.
    """
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(""),  # boş — yeniden denenmeli
                model_result(tool_calls=[tool_call("write_file", path="a.py", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})

    sonuc = await run_agent("bir sey yap", deps)

    assert provider.calls == 3, "boş cevaptan sonra devam edilmeli"
    assert (tmp_path / "a.py").exists(), "iş yapılmalı"
    assert sonuc.final_text == TAM_CEVAP


async def test_israrli_bos_cevapta_sonsuz_donguye_girilmez(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("") for _ in range(10)]))
    deps = _deps(tmp_path, sink, runtime={"self_review": False})

    await run_agent("bir sey yap", deps)

    assert provider.calls <= 3, f"boş cevap {provider.calls} kez denendi — sınır aşıldı"


# --- iş yapmadan kullanıcıya soru sorma ------------------------------------ #
#
# Gözlemlendi (Gemini web): model sekiz araç çağırıp dizin yapısını okudu, sonra
# hiçbir şey değiştirmeden "ne yapmak istediğinizi belirtin" diyerek turu bitirdi.
# Kullanıcı görevi zaten vermişti. Eski kapı (`_stopped_without_acting`) bunu
# yakalayamıyordu: yalnızca BUGFIX/FEATURE gibi türlerde çalışıyor, "analiz et"
# sınıfına düşen istek kapının tamamen dışında kalıyordu.


async def test_is_yapmadan_soru_soran_tur_bir_kez_devam_ettirilir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result("Dizin yapısı `src/app.py` altında incelendi. Ne yapmamı istersiniz?"),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("projeyi analiz et", _deps(tmp_path, sink))

    assert provider.calls == 3
    assert _icerir(sonuc, reflexion.ASKED_INSTEAD_OF_ACTING_NOTE)


async def test_ask_user_cagiran_tur_zorlanmaz(monkeypatch, tmp_path, sink):
    """Model doğru aracı kullandıysa kapı susar; soru meşrudur."""
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("ask_user", question="hangisi?")]),
                model_result("Seçime göre `src/app.py:10` güncellenecek. Onaylar mısınız?"),
            ]
        ),
    )

    sonuc = await run_agent("yap", _deps(tmp_path, sink, asker=ScriptedAsker("ilki")))

    assert provider.calls == 2
    assert not _icerir(sonuc, reflexion.ASKED_INSTEAD_OF_ACTING_NOTE)


async def test_soru_isareti_olmayan_salt_okuma_cevabi_zorlanmaz(monkeypatch, tmp_path, sink):
    """Okuyup açıklayan meşru tur ek çağrı harcamamalı."""
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("bu dizini açıkla", _deps(tmp_path, sink))

    assert provider.calls == 2


# --- "değişiklik yapılmadı" yüklemi ---------------------------------------- #


async def test_salt_okuma_turu_degisiklik_yapmadi_bildirir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert sonuc.made_no_changes is True


async def test_yazan_tur_degisiklik_yapmadi_demez(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("yaz", _deps(tmp_path, sink))

    assert sonuc.mutating_tool_calls_made > 0
    assert sonuc.made_no_changes is False


async def test_araçsiz_sohbet_turu_rozet_kosulunu_tetiklemez(monkeypatch, tmp_path, sink):
    """Düz sohbette kimse değişiklik beklemiyordu; rozet gürültü olurdu."""
    _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    sonuc = await run_agent("selam", _deps(tmp_path, sink))

    assert sonuc.made_no_changes is False


# --- düzeltici tur görevi taşır ve cevabı iki kez basmaz -------------------- #
#
# Gerçek koşu: öz-denetim "sorun bulundu" dedi, düzeltici tur açıldı ve model
# dizini baştan listeleyip "iş henüz verilmedi, ne yapmamı istiyorsunuz" diyerek
# turu bitirdi — birinci turda yapılmış işi de götürerek. Talimat yalnızca
# "bir öz-denetim şu sorunu işaret etti" diyordu; hedef hiçbir yerde yoktu.
#
# Aynı koşuda cevap ekrana YAPIŞIK İKİ KEZ düştü: düzeltici tur `depth=0`
# olduğu için o da nihai cevabını yayınlıyordu.


def test_duzeltici_tur_talimati_kullanicinin_gorevini_tasir():
    from fusion_cli.core.budget import TurnBudget
    from fusion_cli.core.clock import SystemClock
    from fusion_cli.engines.agent.loop import _correction_task

    butce = TurnBudget(
        clock=SystemClock(),
        max_model_calls=10,
        max_verify_rounds=1,
        max_empty_retries=1,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=3,
    )
    butce.successful_tool_evidence.append(("read_file", {"path": "app/page.tsx"}, True))
    metin = _correction_task("dashboard'ı çalışır hale getir", "hiçbir dosya değişmedi", butce)

    assert "dashboard'ı çalışır hale getir" in metin
    assert "sıfırdan başlamıyorsun" in metin
    assert "hiçbir dosya değişmedi" in metin
    assert "read_file(app/page.tsx)" in metin, "zaten yapılanlar hatırlatılmalı"


async def test_ic_tur_nihai_cevabi_yayinlamaz(monkeypatch, tmp_path, sink):
    """`internal=True` turlar `TurnAnswered` yayınlamaz; dış tur tek kez basar."""
    from fusion_cli.core.events import TurnAnswered

    _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    await run_agent("gorev", _deps(tmp_path, sink), internal=True)

    assert not [olay for olay in sink.events if isinstance(olay, TurnAnswered)]


async def test_cevap_tam_olarak_bir_yoldan_ulasir(monkeypatch, tmp_path, sink):
    """Değişmez: akış ve duyuru ASLA aynı anda çalışmaz.

    Gerçekten akıtan sağlayıcıda cevap zaten ekrana ulaşmıştır ve `TurnAnswered`
    susar; akıtmayan web adaptöründe tersi olur. İkisinin birden çalıştığı gün
    cevap iki kez basılır.
    """
    from fusion_cli.core.events import TurnAnswered

    _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink))

    duyurular = [olay for olay in sink.events if isinstance(olay, TurnAnswered)]
    assert sonuc.answer_streamed != bool(duyurular), "iki yol birden ya çalıştı ya sustu"


# --- düzenleme döngüsünden çıkış ------------------------------------------- #
#
# Ölçüldü: `edit_file` beş kez üst üste "'old' metni dosyada bulunamadı" verdi.
# Model her seferinde DAHA DAR bir pencere okuyup aynı yaklaşımı tekrarladı ve
# turun tamamı bu döngüde yandı. Genel refleksiyon notu yetmiyor: model onu
# "biraz daha oku" diye yorumluyor. Çıkış yolu adıyla gösterilmeli.


async def test_tekrarlayan_basarisiz_duzenleme_cikis_yolu_gosterir(monkeypatch, tmp_path, sink):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("edit_file", path="a.py", old="yok1", new="z")]),
                model_result(tool_calls=[tool_call("edit_file", path="a.py", old="yok2", new="z")]),
                model_result(tool_calls=[tool_call("edit_file", path="a.py", old="yok3", new="z")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("a.py'yi düzelt", _deps(tmp_path, sink))

    notlar = [m.content for m in sonuc.messages if "[düzenleme-döngüsü]" in m.content]
    assert notlar, "döngü kapısı hiç konuşmadı"
    assert "multi_edit" in notlar[0] and "write_file" in notlar[0]


async def test_okuma_hatasi_duzenleme_dongusu_sayilmaz(monkeypatch, tmp_path, sink):
    """Yanlış dosya adı bir döngü değildir; o kapıyı tetiklememeli."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="yok1.py")]),
                model_result(tool_calls=[tool_call("read_file", path="yok2.py")]),
                model_result(tool_calls=[tool_call("read_file", path="yok3.py")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert not [m for m in sonuc.messages if "[düzenleme-döngüsü]" in m.content]


def test_devam_et_ilk_gorevin_butcesini_miras_alir():
    """Kısa devam mesajı, sürdürdüğü büyük görevin bütçesini almalı."""
    from fusion_cli.core.types import Message as Msg
    from fusion_cli.engines.agent.classify import TaskKind, classify_task
    from fusion_cli.engines.agent.loop import _scoped_task

    gecmis = [Msg("user", "dashboard'ı çalışır hale getir ve eksik dosyaları oluştur")]

    assert classify_task(_scoped_task("devam et", gecmis)) is TaskKind.FEATURE
    assert classify_task("devam et") is not TaskKind.FEATURE


# --- cevap öğrenmeden ÖNCE duyurulur --------------------------------------- #
#
# Ölçüldü (gerçek koşu): iş bir dakikada bitti, cevap hazırdı, ama ders çıkarımı
# bitene kadar ekrana hiçbir şey basılmadı — kullanıcı 20 dakika boş ekran gördü
# ve turun donduğunu sandı. Öğrenme muhasebedir; kullanıcıyı bekletemez.


async def test_cevap_ders_cikariminden_once_duyurulur(monkeypatch, tmp_path, sink):
    from fusion_cli.core.events import LessonsLearned, TurnAnswered

    sira: list[str] = []

    async def _yavas_ogrenme(task, outcome, deps, **kwargs):
        sira.append("ogrenme")
        deps.publisher.publish(LessonsLearned(count=1))

    monkeypatch.setattr(agent_loop.learning_steps, "learn", _yavas_ogrenme)

    class _Kaydeden:
        def __init__(self, inner):
            self._inner = inner

        def handle(self, event):
            if isinstance(event, TurnAnswered):
                sira.append("cevap")
            self._inner.handle(event)

    class _AkitmayanSaglayici:
        """Web adaptörü gibi: metni akıtmaz, yalnızca sonuç döndürür."""

        def __init__(self, results):
            self._results = list(results)
            self.calls = 0

        @property
        def label(self):
            return "akitmayan"

        async def complete(self, request):
            index = min(self.calls, len(self._results) - 1)
            self.calls += 1
            return self._results[index]

        async def stream(self, request):
            from fusion_cli.core.types import StreamDone

            yield StreamDone(await self.complete(request))

    _kur(
        monkeypatch,
        _AkitmayanSaglayici(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, _Kaydeden(sink))

    await run_agent("gorev", deps)

    assert sira, "ne cevap ne öğrenme yayınlandı"
    assert sira[0] == "cevap", f"öğrenme cevaptan önce çalıştı: {sira}"


async def test_asili_kalan_ders_cikarimi_turu_bekletmez(monkeypatch, tmp_path, sink):
    """Öğrenme bir iyileştirmedir; sınırı aşarsa atlanır, tur normal biter."""
    import asyncio as _asyncio

    from fusion_cli.engines.agent import learning_steps

    monkeypatch.setattr(learning_steps, "LEARN_TIMEOUT_S", 0.05)

    async def _asili() -> None:
        await _asyncio.sleep(10)

    await learning_steps._bounded(_asili())  # zaman aşımı yutulur, hata fırlatmaz


async def test_dogrulama_komutu_degisiklikten_sonra_tekrar_calisabilir(monkeypatch, tmp_path, sink):
    """Düzeltmeden sonra testi tekrar çalıştırmak meşrudur; engellenmemeli.

    Ölçüldü: model kodu düzeltti, `npm test` çalıştırmak istedi ve
    TOOL_CALL_DUPLICATE ile engellendi — düzeltmenin işe yarayıp yaramadığını
    doğrulayamadı.
    """
    (tmp_path / "a.txt").write_text("eski\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("run_shell", command="echo kontrol")]),
                model_result(
                    tool_calls=[tool_call("edit_file", path="a.txt", old="eski", new="yeni")]
                ),
                model_result(tool_calls=[tool_call("run_shell", command="echo kontrol")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("a.txt'yi düzelt ve doğrula", _deps(tmp_path, sink))

    engellenen = [m for m in sonuc.messages if "TOOL_CALL_DUPLICATE" in m.content]
    assert not engellenen, "değişiklikten sonraki doğrulama engellendi"


async def test_degisiklik_olmadan_ayni_komut_yine_tekrar_sayilir(monkeypatch, tmp_path, sink):
    """Çalışma alanı değişmeden ısrarla aynı komut yine tekrardır.

    Sınır okuma araçlarınınkiyle aynıdır (`max_same_tool_without_change`): birkaç
    tekrara izin verilir, ısrar engellenir.
    """
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("run_shell", command="echo x")]),
                model_result(tool_calls=[tool_call("run_shell", command="echo x")]),
                model_result(tool_calls=[tool_call("run_shell", command="echo x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("çalıştır", _deps(tmp_path, sink))

    assert [m for m in sonuc.messages if "TOOL_CALL_DUPLICATE" in m.content]


async def test_dusen_duzenlemeden_sonra_yeniden_okuma_engellenmez(monkeypatch, tmp_path, sink):
    """Toparlanmanın tek yolu yeniden okumaktır; tekrar kapısı onu kesmemeli.

    Ölçüldü (canlı koşu): `edit_file` "'old' bulunamadı" dedi, model dosyayı
    yeniden okumak istedi, TOOL_CALL_DUPLICATE ile engellendi ve tur "3 turdur
    ilerleme yok" ile öldü. Çalışma alanı değişmemişti ama modelin BİLGİ durumu
    değişmek zorundaydı.
    """
    (tmp_path / "a.txt").write_text("gerçek içerik\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(tool_calls=[tool_call("edit_file", path="a.txt", old="YOK", new="x")]),
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("a.txt'yi düzelt", _deps(tmp_path, sink))

    assert not [m for m in sonuc.messages if "TOOL_CALL_DUPLICATE" in m.content]


async def test_dusen_duzenleme_ayni_duzenlemeyi_serbest_birakmaz(monkeypatch, tmp_path, sink):
    """Değiştirici imza çağdan bağımsızdır: aynı yazma yine tekrardır."""
    (tmp_path / "a.txt").write_text("gerçek\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("edit_file", path="a.txt", old="YOK", new="x")]),
                model_result(tool_calls=[tool_call("edit_file", path="a.txt", old="YOK", new="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("düzelt", _deps(tmp_path, sink))

    assert [m for m in sonuc.messages if "TOOL_CALL_DUPLICATE" in m.content]


# --- planlı işte devam bütçesi bekleyen maddelerle büyür ------------------- #
#
# Sabit tek hak PLANLI işlerde yanlıştı: altı maddelik bir todo listesi yazan
# model tek dürtü alıp turu bitiriyordu — yani plan yapmak işi bitirmeye
# yaramıyordu. Geniş görevlerin tek turda bitmemesinin sebeplerinden biri buydu.


def test_devam_hakki_bekleyen_madde_basina_buyur():
    from fusion_cli.core.budget import TurnBudget
    from fusion_cli.core.clock import SystemClock

    butce = TurnBudget(
        clock=SystemClock(),
        max_model_calls=50,
        max_verify_rounds=1,
        max_empty_retries=1,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=5,
    )

    # Bekleyen madde yokken tek hak.
    assert butce.take_auto_continue() is True
    assert butce.take_auto_continue() is False
    # Üç bekleyen madde üç hak daha açar.
    assert [butce.take_auto_continue(pending_todos=3) for _ in range(3)] == [True, True, True]
    assert butce.take_auto_continue(pending_todos=3) is False


def test_todo_bekleyen_sayisi_tamamlananlari_saymaz():
    from fusion_cli.core.tools import TodoItem, TodoList, TodoStatus

    liste = TodoList()
    liste.replace(
        (
            TodoItem("bitti", TodoStatus.COMPLETED),
            TodoItem("sürüyor", TodoStatus.IN_PROGRESS),
            TodoItem("bekliyor", TodoStatus.PENDING),
        )
    )

    assert liste.pending_count == 2
    assert liste.has_pending is True


async def test_degisen_dosyalar_modele_olgu_olarak_bildirilir(monkeypatch, tmp_path, sink):
    """Model kendi işini takip edemiyor; kayıt geçmişe olgu olarak girmeli.

    Ölçüldü: model üç dosya oluşturdu ve kapanışta "herhangi bir değişiklik
    yapılmamıştır" dedi.
    """
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(tool_calls=[tool_call("write_file", path="b.txt", content="y")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("iki dosya oluştur", _deps(tmp_path, sink))

    kayitlar = [m.content for m in sonuc.messages if "[kayıt]" in m.content]
    assert kayitlar, "değişiklik kaydı modele hiç bildirilmedi"
    assert "a.txt" in kayitlar[-1] and "b.txt" in kayitlar[-1]


async def test_degisiklik_yoksa_kayit_eklenmez(monkeypatch, tmp_path, sink):
    """Salt-okuma turunda kayıt promptu şişirmemeli."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert not [m for m in sonuc.messages if "[kayıt]" in m.content]


# --- doğrulama kapısı gerçekten çağrılıyor mu ------------------------------ #
#
# Canlı koşuda model `app/page.tsx`'e yinelenen fonksiyon tanımları ekledi, proje
# `tsc` ile 8 hata verdi ve tur BAŞARI özetiyle kapandı. Doğrulayıcı elle
# çağrıldığında hatayı yakalıyordu; yani sorun kapının kendisinde değil,
# motorun onu çağırıp çağırmadığındaydı.


class _DusenDogrulayici:
    def __init__(self) -> None:
        self.calls = 0

    async def verify(self):
        from fusion_cli.core.verification import VerificationResult

        self.calls += 1
        return VerificationResult(ok=False, summary="derleme kırıldı", findings=("hata",))


async def test_degisiklik_yapan_tur_dogrulamadan_gecer(monkeypatch, tmp_path, sink):
    from fusion_cli.core.events import VerificationFailed

    dogrulayici = _DusenDogrulayici()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.verifier = dogrulayici

    await run_agent("a.txt oluştur", deps)

    assert dogrulayici.calls > 0, "doğrulayıcı hiç çağrılmadı"
    assert [e for e in sink.events if isinstance(e, VerificationFailed)]


async def test_duzeltilemeyen_dogrulama_basari_olarak_kapanmaz(monkeypatch, tmp_path, sink):
    """Bildiğimiz bir bozukluğu başarı diye teslim etmek kabul edilemez.

    Ölçüldü: kapı bozulmayı yakaladı, düzeltici tur açıldı, düzeltme tutmadı,
    hak bitti — ve tur "tamamladım" diyerek kapandı. Kullanıcının projesi 8
    derleme hatasıyla bozuk kaldı.
    """
    dogrulayici = _DusenDogrulayici()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.verifier = dogrulayici

    sonuc = await run_agent("a.txt oluştur", deps)

    assert sonuc.ok is False, "doğrulama düşmüşken tur başarı sayıldı"
    assert "DOĞRULAMA GEÇMEDİ" in sonuc.final_text
    assert "derleme kırıldı" in sonuc.final_text


# --- yanlış çalışma dizini --------------------------------------------------- #
#
# Ölçüldü: kullanıcı fusion'ı yanlış klasörde açtı ve sidebar düzeni hakkında bir
# görev verdi. Model görevde geçen dört dosyayı da bulamadı; ardından öz-denetim
# düzeltici turunda GÖREVİ TERK ETTİ ve kendine yeni iş uydurdu — o projenin
# README'sini okuyup "test paketini çalıştır, hataları düzelt" diye todo listesi
# yazdı. Kullanıcının sorduğu şeyle hiçbir ilgisi yoktu.


async def test_dosyalarin_hicbiri_yoksa_yanlis_dizin_uyarisi_gider(monkeypatch, tmp_path, sink):
    from fusion_cli.engines.agent import reflexion as r

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="app/globals.css")]),
                model_result(tool_calls=[tool_call("read_file", path="components/Sidebar.tsx")]),
                model_result(tool_calls=[tool_call("read_file", path="app/page.tsx")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("sidebar düzenini düzelt", _deps(tmp_path, sink))

    notlar = [m.content for m in sonuc.messages if "[yanlış-dizin]" in m.content]
    assert notlar, "yanlış dizin uyarısı hiç gitmedi"
    assert "DUR" in notlar[0]
    assert "UYDURMA" in notlar[0]
    assert r.WRONG_WORKSPACE_NOTE.split("{")[0] in notlar[0]


async def test_tek_dosya_okunabiliyorsa_uyari_gitmez(monkeypatch, tmp_path, sink):
    """Dizin doğru ama model yanlış ad tahmin etmiş olabilir; bu uyarı değildir."""
    (tmp_path / "var.txt").write_text("içerik\n", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="yok1.css")]),
                model_result(tool_calls=[tool_call("read_file", path="yok2.tsx")]),
                model_result(tool_calls=[tool_call("read_file", path="var.txt")]),
                model_result(tool_calls=[tool_call("read_file", path="yok3.tsx")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("bak", _deps(tmp_path, sink))

    assert not [m for m in sonuc.messages if "[yanlış-dizin]" in m.content]


async def test_uyari_bir_kez_verilir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path=f"yok{i}.tsx")])
                for i in range(6)
            ]
            + [model_result(TAM_CEVAP)]
        ),
    )

    sonuc = await run_agent("düzelt", _deps(tmp_path, sink))

    assert len([m for m in sonuc.messages if "[yanlış-dizin]" in m.content]) == 1


async def test_yanlis_dizinde_oz_denetim_turu_acilmaz(monkeypatch, tmp_path, sink):
    """Yanlış dizinde düzeltilecek bir şey yok; düzeltici tur iş uyduruyordu."""
    from fusion_cli.core.events import SelfReviewStarted

    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.css")]),
                model_result(tool_calls=[tool_call("read_file", path="b.tsx")]),
                model_result(tool_calls=[tool_call("read_file", path="c.tsx")]),
                model_result("Bu dizinde aradığın dosyalar yok; doğru projede çalıştır."),
            ]
        ),
    )

    sonuc = await run_agent("sidebar düzelt", _deps(tmp_path, sink, runtime={"self_review": True}))

    assert sonuc.wrong_workspace is True
    assert not [e for e in sink.events if isinstance(e, SelfReviewStarted)]
    assert provider.calls == 4, "fazladan düzeltici tur açılmamalı"
