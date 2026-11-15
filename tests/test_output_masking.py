"""Kayan pencere maskeleme: eski araç sonuçları EŞİK BEKLEMEDEN yer tutucuya iner.

Kaynak: JetBrains (arXiv 2508.21433) eski gözlemleri gizlemenin özetleme kadar iyi ve
~%50 ucuz olduğunu, SWE-agent son ~5 gözlemi tam tutmanın tam geçmişten iyi olduğunu
ölçtü. Burada sınanan: model görünümü küçülür, kalıcı kayıt DEĞİŞMEZ, paralel çağrıların
sonuçları ve hatalar maskelenmez, bir kez maskelenen mesaj bir daha değişmez.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.artifacts import ArtifactStore, offload_output
from fusion_cli.core.events import ToolOutputsMasked
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import history, masking
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.loop import run_agent

from .fakes import ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur

BUYUK = "x" * 1_000


@pytest.fixture
def sink():
    from .fakes import RecordingSink

    return RecordingSink()


def _cagri(kimlik: str, ad: str = "read_file", **arguman: object) -> ToolCall:
    return ToolCall(id=kimlik, name=ad, arguments=json.dumps(arguman))


def _konusma(
    tur_sayisi: int, cikti: str = BUYUK, *, ad: str = "read_file", ok: bool = True
) -> list[Message]:
    mesajlar = [Message("system", "kimlik"), Message("user", "görev")]
    for index in range(tur_sayisi):
        cagri = _cagri(str(index), ad, path=f"src/dosya{index}.py")
        mesajlar.append(Message("assistant", "", tool_calls=(cagri,)))
        mesajlar.append(Message("tool", cikti, name=ad, tool_call_id=str(index), ok=ok))
    return mesajlar


def _tam_mi(mesaj: Message) -> bool:
    return not mesaj.content.startswith(masking.MASK_PREFIX)


def test_pencere_disindaki_eski_sonuclar_yer_tutucuya_iner_kalici_kayit_degismez():
    mesajlar = _konusma(20)
    kopya = list(mesajlar)

    gorunum = masking.mask_view(mesajlar, 5, masking.MaskLedger())

    assert mesajlar == kopya and all(a is b for a, b in zip(mesajlar, kopya, strict=True))
    araclar = [m for m in gorunum.messages if m.role == "tool"]
    assert [_tam_mi(m) for m in araclar[-5:]] == [True] * 5
    assert all(not _tam_mi(m) for m in araclar[: -5 - masking.batch_size(5) + 1][:3])
    assert gorunum.masked > 0
    assert len(gorunum.messages) == len(mesajlar)
    assert [m.tool_call_id for m in gorunum.messages] == [m.tool_call_id for m in mesajlar]


def test_yer_tutucu_arac_adini_argumani_durumu_boyutu_ve_yeniden_calistirma_notunu_tasir():
    mesajlar = _konusma(12)

    gorunum = masking.mask_view(mesajlar, 3, masking.MaskLedger())

    yer_tutucu = next(m.content for m in gorunum.messages if m.role == "tool")
    assert yer_tutucu.startswith(masking.MASK_PREFIX)
    assert "read_file" in yer_tutucu
    assert "src/dosya0.py" in yer_tutucu
    assert "1.000 karakter" in yer_tutucu or "1000 karakter" in yer_tutucu
    assert "yeniden" in yer_tutucu
    assert len(yer_tutucu) < len(BUYUK) // 2


def test_son_asistan_mesajindan_sonraki_tum_paralel_sonuclar_pencereden_bagimsiz_tam_kalir():
    """A1-01 düzeltmesinin korunması: 12 paralel çağrının 12 sonucu da, pencere 3 olsa da."""
    mesajlar = _konusma(10)
    cagrilar = tuple(_cagri(f"p{i}", path=f"p{i}.py") for i in range(12))
    mesajlar.append(Message("assistant", "", tool_calls=cagrilar))
    for i in range(12):
        mesajlar.append(Message("tool", BUYUK, name="read_file", tool_call_id=f"p{i}", ok=True))

    gorunum = masking.mask_view(mesajlar, 3, masking.MaskLedger())

    paralel = [m for m in gorunum.messages if (m.tool_call_id or "").startswith("p")]
    assert len(paralel) == 12 and all(_tam_mi(m) for m in paralel)
    assert any(not _tam_mi(m) for m in gorunum.messages if m.role == "tool")


def test_hata_sonuclari_maskelenmez():
    mesajlar = _konusma(15, ok=False)

    gorunum = masking.mask_view(mesajlar, 3, masking.MaskLedger())

    assert gorunum.masked == 0
    assert gorunum.messages == mesajlar


def test_kisa_sonuclar_maskelenmez():
    mesajlar = _konusma(15, cikti="y" * (masking.MIN_MASK_CHARS - 1))

    gorunum = masking.mask_view(mesajlar, 3, masking.MaskLedger())

    assert gorunum.masked == 0


def test_kullanici_mesajlari_ozetler_ve_kural_dosyalari_maskelenmez():
    mesajlar = _konusma(2)
    mesajlar.insert(2, Message("user", "main'e asla push etme. " + BUYUK))
    mesajlar.insert(3, Message("user", f"{history.STEPS_SUMMARY_PREFIX}\n" + BUYUK))
    # Kural dosyası okuması + kullanıcıya sorulan sorunun cevabı da korunur.
    mesajlar.append(Message("assistant", "", tool_calls=(_cagri("k", path="CLAUDE.md"),)))
    mesajlar.append(Message("tool", BUYUK, name="read_file", tool_call_id="k", ok=True))
    mesajlar.append(Message("assistant", "", tool_calls=(_cagri("u", "ask_user"),)))
    mesajlar.append(Message("tool", BUYUK, name="ask_user", tool_call_id="u", ok=True))
    for i in range(10):
        mesajlar.append(Message("assistant", "", tool_calls=(_cagri(f"z{i}", path="a.py"),)))
        mesajlar.append(Message("tool", BUYUK, name="read_file", tool_call_id=f"z{i}", ok=True))

    gorunum = masking.mask_view(mesajlar, 2, masking.MaskLedger())

    kullanicilar = [m for m in gorunum.messages if m.role == "user"]
    assert kullanicilar == [m for m in mesajlar if m.role == "user"]
    by_id = {m.tool_call_id: m for m in gorunum.messages if m.role == "tool"}
    assert _tam_mi(by_id["k"]) and _tam_mi(by_id["u"])
    assert not _tam_mi(by_id["0"])


def test_pencere_sifirsa_kapali_gorunum_ayni_mesajlari_doner():
    mesajlar = _konusma(20)

    gorunum = masking.mask_view(mesajlar, 0, masking.MaskLedger())

    assert gorunum.messages == mesajlar and gorunum.masked == 0 and gorunum.saved_chars == 0


def test_diske_alinmis_cikti_yer_tutucuda_yolunu_korur(tmp_path):
    depo = ArtifactStore(tmp_path / "artifacts")
    uzun, yol = offload_output("satir\n" * 10_000, store=depo, tool="run_shell", limit=20_000)
    assert yol is not None
    mesajlar = _konusma(10)
    mesajlar[3] = Message("tool", uzun, name="run_shell", tool_call_id="0", ok=True)

    gorunum = masking.mask_view(mesajlar, 2, masking.MaskLedger())

    yer_tutucu = gorunum.messages[3].content
    assert yer_tutucu.startswith(masking.MASK_PREFIX)
    assert str(yol) in yer_tutucu
    assert len(yer_tutucu) < 800


def test_gorselli_eski_sonuc_gorselini_birakir():
    mesajlar = _konusma(10)
    mesajlar[3] = Message(
        "tool", "kısa", name="desktop_screenshot", tool_call_id="0", ok=True, images=("data:x",)
    )

    gorunum = masking.mask_view(mesajlar, 2, masking.MaskLedger())

    assert gorunum.messages[3].images == ()
    assert not _tam_mi(gorunum.messages[3])


def test_bir_kez_maskelenen_mesaj_bir_daha_degismez_ve_onek_toplu_kayar():
    """Önbellek: pencere her turda 1 mesaj kaymaz; seri halinde (toplu) kayar."""
    ledger = masking.MaskLedger()
    mesajlar = [Message("system", "kimlik"), Message("user", "görev")]
    onceki: list[str] | None = None
    onek_bozulan_tur = 0
    maskelenen_tur = 0
    adim = 40
    for index in range(adim):
        mesajlar.append(Message("assistant", "", tool_calls=(_cagri(str(index), path=f"{index}"),)))
        mesajlar.append(Message("tool", BUYUK, name="read_file", tool_call_id=str(index), ok=True))
        gorunum = masking.mask_view(mesajlar, 6, ledger)
        simdiki = [m.content for m in gorunum.messages]
        if onceki is not None:
            # Daha önce gönderilen her mesaj aynı kalmalı ya da yer tutucuya inmeli;
            # yer tutucu bir daha DEĞİŞMEMELİ.
            for eski, yeni in zip(onceki, simdiki, strict=False):
                if eski.startswith(masking.MASK_PREFIX):
                    assert yeni == eski
            if any(
                e != y for e, y in zip(onceki, simdiki, strict=False)
            ):  # önceden gönderilmiş önek değişti
                onek_bozulan_tur += 1
        if gorunum.newly_masked:
            maskelenen_tur += 1
        onceki = simdiki
    # Her turda değil, yalnız toplu kayma anlarında.
    assert 0 < onek_bozulan_tur <= adim // masking.batch_size(6) + 1
    assert maskelenen_tur == onek_bozulan_tur


def test_istatistik_kazanilan_karakter_gercek_farka_esittir():
    mesajlar = _konusma(25)

    gorunum = masking.mask_view(mesajlar, 4, masking.MaskLedger())

    assert gorunum.saved_chars == history.total_chars(mesajlar) - history.total_chars(
        gorunum.messages
    )
    assert gorunum.saved_chars > 0
    assert gorunum.masked == sum(1 for m in gorunum.messages if not _tam_mi(m))


def test_onizleme_modu_defteri_degistirmez_ama_ayni_gorunumu_verir():
    mesajlar = _konusma(25)
    defter = masking.MaskLedger()

    onizleme = masking.mask_view(mesajlar, 4, defter, commit=False)
    assert len(defter) == 0
    gercek = masking.mask_view(mesajlar, 4, defter)

    assert onizleme.messages == gercek.messages
    assert len(defter) == gercek.masked


# --------------------------------------------------------------------------- #
# Döngüye bağlama


async def test_dongu_modele_maskeli_gorunum_gonderir_kalici_kayit_tam_kalir(
    monkeypatch, tmp_path, sink
):
    for index in range(14):
        (tmp_path / f"d{index}.txt").write_text(f"{index}-" + "z" * 2_000, encoding="utf-8")
    saglayici = ScriptedProvider(
        [
            *[
                model_result(tool_calls=[tool_call("read_file", path=f"d{index}.txt")])
                for index in range(14)
            ],
            model_result("Hepsi okundu; değişiklik gerekmedi."),
        ]
    )
    _kur(monkeypatch, saglayici)

    sonuc = await run_agent(
        "dosyaları oku",
        _deps(tmp_path, sink, runtime={"agent_max_steps": 50, "tool_output_window": 4}),
        system_prompt="Dosyaları oku.",
    )

    son_istek = saglayici.seen_messages[-1]
    tool_gorunum = [m for m in son_istek if m.role == "tool"]
    assert any(m.content.startswith(masking.MASK_PREFIX) for m in tool_gorunum)
    assert all(not m.content.startswith(masking.MASK_PREFIX) for m in tool_gorunum[-4:])
    # Kalıcı kayıt maskesiz.
    kalici = [m for m in sonuc.messages if m.role == "tool"]
    assert not any(m.content.startswith(masking.MASK_PREFIX) for m in kalici)
    olaylar = [e for e in sink.events if isinstance(e, ToolOutputsMasked)]
    assert olaylar and olaylar[-1].masked > 0 and olaylar[-1].saved_chars > 0
    assert olaylar[-1].window == 4


async def test_dongu_pencere_sifirsa_maskelemez_ve_olay_yayinlamaz(monkeypatch, tmp_path, sink):
    for index in range(10):
        (tmp_path / f"d{index}.txt").write_text("z" * 2_000, encoding="utf-8")
    saglayici = ScriptedProvider(
        [
            *[
                model_result(tool_calls=[tool_call("read_file", path=f"d{index}.txt")])
                for index in range(10)
            ],
            model_result("bitti"),
        ]
    )
    _kur(monkeypatch, saglayici)

    await run_agent(
        "oku",
        _deps(tmp_path, sink, runtime={"agent_max_steps": 50, "tool_output_window": 0}),
        system_prompt="Oku.",
    )

    assert not any(m.content.startswith(masking.MASK_PREFIX) for m in saglayici.seen_messages[-1])
    assert not any(isinstance(e, ToolOutputsMasked) for e in sink.events)


def test_batch_size_pencereden_turetilir():
    assert masking.batch_size(1) == 1
    assert masking.batch_size(8) == 4
    assert agent_loop is not None


async def test_maskelenmis_okuma_yer_tutucunun_dedigi_gibi_yeniden_okunabilir(
    monkeypatch, tmp_path, sink
):
    """Yer tutucu "gerekirse yeniden oku" der; tekrar kapısı (önbellekten not ya da
    REPEAT_BLOCK_AT engeli) bu meşru yeniden okumayı cezalandırmamalı: her okuma TAM
    sonucu vermeli."""
    (tmp_path / "ana.txt").write_text("ANA-" + "q" * 1_500, encoding="utf-8")
    adimlar = []
    for k in range(6):
        for ad in (f"f{k}.txt", f"g{k}.txt"):
            (tmp_path / ad).write_text(ad + "-" + "w" * 1_500, encoding="utf-8")
        adimlar += [
            model_result(tool_calls=[tool_call("read_file", path="ana.txt")]),
            model_result(tool_calls=[tool_call("read_file", path=f"f{k}.txt")]),
            model_result(tool_calls=[tool_call("read_file", path=f"g{k}.txt")]),
        ]
    saglayici = ScriptedProvider([*adimlar, model_result("bitti")])
    _kur(monkeypatch, saglayici)

    sonuc = await run_agent(
        "oku",
        _deps(tmp_path, sink, runtime={"agent_max_steps": 60, "tool_output_window": 2}),
        system_prompt="Oku.",
    )

    ana = [m for m in sonuc.messages if m.role == "tool" and "ANA-" in m.content]
    assert len(ana) == 6
    assert all(m.ok and not m.content.startswith("TOOL_CALL") for m in ana)
    engelli = [m for m in sonuc.messages if m.role == "tool" and m.ok is False]
    assert engelli == []


def test_api_ve_temizlik_ayni_pin_kimligini_ayni_sinirla_korur():
    messages = _konusma(12, cikti="özgün kanıt " + "z" * 4_000)
    pins = frozenset({"0"})
    ledger = masking.MaskLedger()
    masking.mask_view(messages, 2, ledger)
    view = masking.mask_view(messages, 2, ledger, pinned_call_ids=pins)
    cleared = history.clear_old_tool_outputs(messages, 3_000, pinned_call_ids=pins)
    assert view.messages[3].content == cleared[3].content
    assert view.messages[3].content.startswith("özgün kanıt ")
    assert len(view.messages[3].content) <= 1_500
    released = masking.mask_view(messages, 2, ledger)
    assert released.messages[3].content.startswith(masking.MASK_PREFIX)
    assert messages[3].content == "özgün kanıt " + "z" * 4_000


@pytest.mark.parametrize("window", [0, 1, 3])
def test_pinler_son_gorulmemis_paralel_grubun_tum_sonuclarini_tam_birakir(window):
    messages = _konusma(5, cikti="z" * 4_000)
    calls = tuple(_cagri(f"parallel{i}") for i in range(5))
    messages.append(Message("assistant", "", tool_calls=calls))
    for call in calls:
        messages.append(Message("tool", "taze" * 2_000, tool_call_id=call.id))
    pins = frozenset(call.id for call in calls)
    view = masking.mask_view(messages, window, masking.MaskLedger(), pinned_call_ids=pins)
    cleared = history.clear_old_tool_outputs(messages, 1, pinned_call_ids=pins)
    assert view.messages[-5:] == messages[-5:]
    assert cleared[-5:] == messages[-5:]
