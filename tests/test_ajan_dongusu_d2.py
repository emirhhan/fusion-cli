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
