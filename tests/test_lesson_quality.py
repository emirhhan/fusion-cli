"""Faz 1 — yerel ders kalitesi: güven decay'i, sıralama, yazım kapısı, sır tespiti.

Hepsi saf fonksiyon olarak, ağ/ChromaDB olmadan test edilir. Depoya dokunan geriye
dönük uyumluluk ve reinforce testleri `slow` işaretiyle ayrıca çalışır.
"""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl.commands import parse_lesson_selection
from fusion_cli.core.memory import DEFAULT_LESSON_CONFIDENCE, Lesson, LessonKind, LessonSource
from fusion_cli.core.redaction import contains_sensitive
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import learning
from fusion_cli.engines.agent.learning_steps import should_learn
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.memory.lesson_ranking import Candidate, select_lessons
from fusion_cli.memory.lesson_scoring import (
    is_injectable,
    reinforced,
)


def _lesson(text: str, *, kind: LessonKind = LessonKind.SUCCESS, confidence: float = 1.0) -> Lesson:
    return Lesson(text=text, kind=kind, confidence=confidence)


# --------------------------------------------------------------------------- #
# Güven decay'i (reinforced) — saf
# --------------------------------------------------------------------------- #


def test_basari_guveni_artirir_ve_sayaci_yukseltir():
    lesson = _lesson("test calistir", confidence=0.5)
    updated = reinforced(lesson, success=True)
    assert updated.confidence > lesson.confidence
    assert updated.success_count == 1
    assert updated.failure_count == 0


def test_basarisizlik_guveni_dusurur_ve_sayaci_yukseltir():
    lesson = _lesson("test calistir", confidence=0.5)
    updated = reinforced(lesson, success=False)
    assert updated.confidence < lesson.confidence
    assert updated.failure_count == 1
    assert updated.success_count == 0


def test_basarisizlik_basaridan_daha_sert_dususur():
    base = _lesson("x", confidence=0.5)
    kazanc = reinforced(base, success=True).confidence - 0.5
    kayip = 0.5 - reinforced(base, success=False).confidence
    assert kayip > kazanc


def test_guven_sinirlar_icinde_kalir():
    assert reinforced(_lesson("x", confidence=1.0), success=True).confidence == 1.0
    assert reinforced(_lesson("x", confidence=0.0), success=False).confidence == 0.0


def test_reinforced_girdiyi_mutasyona_ugratmaz():
    lesson = _lesson("x", confidence=0.5)
    reinforced(lesson, success=False)
    assert lesson.confidence == 0.5
    assert lesson.failure_count == 0


def test_tekrarli_basarisizlik_dersi_esigin_altina_indirir():
    lesson = _lesson("kotu ders", confidence=1.0)
    for _ in range(10):
        lesson = reinforced(lesson, success=False)
    assert not is_injectable(lesson)


# --------------------------------------------------------------------------- #
# Sıralama ve eşikler (select_lessons) — saf
# --------------------------------------------------------------------------- #


def test_alakasiz_ders_elenir():
    yakin = Candidate(_lesson("alakali"), distance=0.2)
    uzak = Candidate(_lesson("alakasiz"), distance=0.9)
    secilen = select_lessons((yakin, uzak), limit=4)
    assert [ders.text for ders in secilen] == ["alakali"]


def test_dusuk_guvenli_ders_enjekte_edilmez():
    guvenli = Candidate(_lesson("guvenli", confidence=0.9), distance=0.2)
    zehirli = Candidate(_lesson("zehirli", confidence=0.1), distance=0.2)
    secilen = select_lessons((guvenli, zehirli), limit=4)
    assert [ders.text for ders in secilen] == ["guvenli"]


def test_hatalar_basarilardan_once_siralanir():
    basari = Candidate(_lesson("basari", kind=LessonKind.SUCCESS), distance=0.1)
    hata = Candidate(_lesson("hata", kind=LessonKind.MISTAKE), distance=0.3)
    secilen = select_lessons((basari, hata), limit=4)
    assert secilen[0].kind is LessonKind.MISTAKE


def test_esit_turde_yuksek_guven_one_gelir():
    dusuk = Candidate(_lesson("dusuk", confidence=0.5), distance=0.2)
    yuksek = Candidate(_lesson("yuksek", confidence=0.95), distance=0.2)
    secilen = select_lessons((dusuk, yuksek), limit=4)
    assert secilen[0].text == "yuksek"


def test_limit_uygulanir():
    adaylar = tuple(Candidate(_lesson(f"ders{i}"), distance=0.1) for i in range(5))
    assert len(select_lessons(adaylar, limit=2)) == 2


# --------------------------------------------------------------------------- #
# Sır / kişisel veri tespiti
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    [
        "anahtar sk-ABCDEFGH1234567890abcd kullan",
        "token: ghp_ABCDEFGHIJKLMNOP1234567890",  # gitleaks:allow
        "AWS AKIAIOSFODNN7EXAMPLE anahtari",
        "-----BEGIN RSA PRIVATE KEY-----",
        "password=supersecret123",
        "iletisim: ali@example.com",
    ],
)
def test_sir_iceren_metin_yakalanir(text):
    assert contains_sensitive(text) is True


def test_temiz_metin_sir_sayilmaz():
    assert contains_sensitive("Dosyayi degistirmeden once oku.") is False


# --------------------------------------------------------------------------- #
# Yazım kapısı (screen_lesson / screen_lessons) — saf
# --------------------------------------------------------------------------- #


def test_kanitsiz_ders_reddedilir():
    result = learning.screen_lesson(_lesson("bir sey"), (), has_evidence=False)
    assert not result.accepted
    assert "kanıt" in result.reason


def test_sirli_ders_reddedilir():
    lesson = _lesson("anahtar sk-ABCDEFGH1234567890abcd kullanildi")
    result = learning.screen_lesson(lesson, (), has_evidence=True)
    assert not result.accepted


def test_cok_benzer_ders_dedup_ile_reddedilir():
    mevcut = (_lesson("dosyayi degistirmeden once mutlaka oku ve kontrol et"),)
    aday = _lesson("dosyayi degistirmeden once mutlaka oku ve kontrol et ayrica")
    result = learning.screen_lesson(aday, mevcut, has_evidence=True)
    assert not result.accepted


def test_farkli_ders_kabul_edilir():
    mevcut = (_lesson("dosyayi once oku"),)
    aday = _lesson("test kirilinca implementasyonu duzelt sakin testi silme")
    result = learning.screen_lesson(aday, mevcut, has_evidence=True)
    assert result.accepted


def test_celiskili_ders_isaretlenir_ama_kabul_edilir():
    mevcut = (_lesson("multi_edit araci kullan"),)
    aday = _lesson("multi_edit araci kullanma")
    result = learning.screen_lesson(aday, mevcut, has_evidence=True)
    assert result.accepted
    assert result.contradiction is True


def test_screen_lessons_kabul_edilenler_sonrakilere_dedup_uygular():
    aday = _lesson("test kirilinca implementasyonu duzelt sakin testi silme")
    ikiz = _lesson("test kirilinca implementasyonu duzelt sakin testi silme kesinlikle")
    kabul = learning.screen_lessons((aday, ikiz), (), has_evidence=True)
    assert len(kabul) == 1


def test_measurable_evidence_arac_mesajiyla_dogru():
    with_tool = [Message("assistant", "x"), Message("tool", "cikti", ok=True)]
    without_tool = [Message("assistant", "x"), Message("user", "y")]
    assert learning.has_measurable_evidence(with_tool) is True
    assert learning.has_measurable_evidence(without_tool) is False


# --------------------------------------------------------------------------- #
# Depo: geriye dönük uyumluluk ve reinforce (gerçek ChromaDB — yavaş)
# --------------------------------------------------------------------------- #


@pytest.mark.slow
def test_eski_kayit_varsayilan_guvenle_okunur(tmp_path):
    """Güven/sayaç alanları taşınmadan yazılmış eski kayıt varsayılanla okunmalı."""
    from fusion_cli.memory.lessons import ChromaLessonMemory, _to_lesson

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="eski ders", kind=LessonKind.SUCCESS))
    # Eski metadata'yı taklit et: yeni alanlar hiç yok.
    eski = _to_lesson("eski ders", {"kind": "success", "source": "seed"})
    assert eski.confidence == DEFAULT_LESSON_CONFIDENCE
    assert eski.success_count == 0
    assert eski.source is LessonSource.SEED


@pytest.mark.slow
def test_reinforce_basarisizlikta_guveni_dusurur(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="denenecek ders", kind=LessonKind.SUCCESS))

    updated = bellek.reinforce(("denenecek ders",), success=False)
    assert updated == 1
    kayit = bellek.all()[0]
    assert kayit.confidence < DEFAULT_LESSON_CONFIDENCE
    assert kayit.failure_count == 1


@pytest.mark.slow
def test_reinforce_eslesmeyen_metni_atlar(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="var olan", kind=LessonKind.SUCCESS))
    assert bellek.reinforce(("olmayan ders",), success=True) == 0


# --------------------------------------------------------------------------- #
# Öğrenme kapısı — başarısız tur belleği zehirlemesin
# --------------------------------------------------------------------------- #


def _tur(**alanlar: object) -> AgentOutcome:
    """Ders kapısı için varsayılan olarak SAĞLIKLI bir tur; alanlar tek tek bozulur."""
    varsayilan: dict[str, object] = {
        "final_text": "bitti",
        "messages": [],
        "tool_calls_made": 2,
        "mutating_tool_calls_made": 1,
        "ok": True,
        "hit_step_limit": False,
        "failed_tool_calls": 0,
    }
    varsayilan.update(alanlar)
    return AgentOutcome(**varsayilan)  # type: ignore[arg-type]


def test_temiz_tur_ogrenilir():
    assert should_learn(_tur(), plan_mode=False) is True


def test_arac_cagrisi_olmayan_sohbet_turu_ogrenilmez():
    assert should_learn(_tur(tool_calls_made=0), plan_mode=False) is False


def test_plan_kipi_ogrenilmez():
    assert should_learn(_tur(), plan_mode=True) is False


def test_ilerleme_yok_kapisiyla_olen_tur_ogrenilmez():
    """Ölçülen zarar: iskele yazıp kilitlenen tur öldürüldü, sonra ders yazıldı."""
    olen = _tur(ok=False, hit_step_limit=True)
    assert should_learn(olen, plan_mode=False) is False


def test_model_hatasiyla_biten_tur_ogrenilmez():
    assert should_learn(_tur(ok=False), plan_mode=False) is False


def test_adim_sinirina_dayanan_tur_ogrenilmez():
    assert should_learn(_tur(hit_step_limit=True), plan_mode=False) is False


def test_hatali_arac_cagrisi_olan_temiz_tur_yine_de_ogrenilir():
    """Hatadan öğrenme kaybolmamalı: model hata yapıp toparladıysa ders değerlidir."""
    toparlanan = _tur(failed_tool_calls=2, ok=True, hit_step_limit=False)
    assert should_learn(toparlanan, plan_mode=False) is True


def test_web_ai_salt_okuma_turu_ogrenilmez():
    salt_okuma = _tur(mutating_tool_calls_made=0, failed_tool_calls=0)
    assert should_learn(salt_okuma, plan_mode=False, allow_read_only=False) is False


# --------------------------------------------------------------------------- #
# Ders denetimi ve silme — /lessons numarası → /forget
# --------------------------------------------------------------------------- #


def test_tek_numara_secilir():
    assert parse_lesson_selection("3", 10) == ((3,), "")


def test_bosluk_ve_virgul_ayracli_liste_secilir():
    assert parse_lesson_selection("3 7,9", 10) == ((3, 7, 9), "")


def test_aralik_genisletilir():
    assert parse_lesson_selection("2-5", 10) == ((2, 3, 4, 5), "")


def test_aralik_ve_tekil_karisik_kullanilir():
    assert parse_lesson_selection("1 3-5 9", 10) == ((1, 3, 4, 5, 9), "")


def test_tekrarli_numara_bir_kez_sayilir():
    assert parse_lesson_selection("3 3 3", 10) == ((3,), "")


def test_bos_argumanda_kullanim_metni_doner():
    numaralar, hata = parse_lesson_selection("   ", 10)
    assert numaralar == () and hata


def test_sayi_olmayan_deger_hata_verir():
    numaralar, hata = parse_lesson_selection("üç", 10)
    assert numaralar == () and "üç" in hata


def test_aralik_disi_numara_sessizce_atlanmaz():
    """Yanlış dersi silmek geri alınamaz; hata vermek atlamaktan iyidir."""
    numaralar, hata = parse_lesson_selection("11", 10)
    assert numaralar == () and hata


def test_sifir_gecersizdir():
    numaralar, hata = parse_lesson_selection("0", 10)
    assert numaralar == () and hata


@pytest.mark.slow
def test_forget_dersi_depodan_gercekten_siler(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="zehirli ders", kind=LessonKind.MISTAKE))
    bellek.add(Lesson(text="iyi ders", kind=LessonKind.SUCCESS))

    silinen = bellek.forget(("zehirli ders",))

    assert silinen == 1
    assert bellek.count() == 1
    assert [ders.text for ders in bellek.all()] == ["iyi ders"]


@pytest.mark.slow
def test_forget_eslesmeyen_metni_atlar(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    bellek.add(Lesson(text="var olan", kind=LessonKind.SUCCESS))

    assert bellek.forget(("olmayan ders",)) == 0
    assert bellek.count() == 1


@pytest.mark.slow
def test_forget_coklu_ders_siler(tmp_path):
    from fusion_cli.memory.lessons import ChromaLessonMemory

    bellek = ChromaLessonMemory(tmp_path)
    for metin in ("bir", "iki", "uc"):
        bellek.add(Lesson(text=metin, kind=LessonKind.SUCCESS))

    assert bellek.forget(("bir", "uc")) == 2
    assert [ders.text for ders in bellek.all()] == ["iki"]


def test_alaka_guveni_ezmez():
    """Ölçüldü: 380 derslik bellekte "stripe ile iade yap" sorgusu, konuyla
    ilgisiz ama güveni 1.00 olan dosya-yazma derslerini getiriyordu.

    Güven, benzer ölçüde alakalı dersler arasında karar vermek içindir; alakanın
    YERİNE geçemez. Sıralama küçük bellekte sorun çıkarmıyordu, bellek büyüyünce
    ilgili ders hiç görünmez oldu.
    """
    uzak_ama_guvenli = Candidate(_lesson("uzak", confidence=1.0), distance=0.60)
    yakin_ama_yeni = Candidate(_lesson("yakin", confidence=0.60), distance=0.15)

    secilen = select_lessons((uzak_ama_guvenli, yakin_ama_yeni), limit=4)

    assert secilen[0].text == "yakin"


def test_kucuk_alaka_farki_guveni_ezmez():
    """Alaka güveni ezmemeli AMA kıl payı alaka farkı da güveni ezmemeli.

    Ölçüldü: alaka tek başına birincil ölçüt yapılınca, uzun ve genel derslerin
    zayıf lexical eşleşmesi baskın hâle geldi ve Godot görevine tek bir Godot
    dersi gelmedi. Alaka KABACA karar verir; benzer yakınlıktakiler arasında
    güven seçer.
    """
    genel = Candidate(_lesson("genel", confidence=1.0), distance=0.34)
    isabetli = Candidate(_lesson("isabetli", confidence=0.6), distance=0.30)

    secilen = select_lessons((genel, isabetli), limit=4)

    assert secilen[0].text == "genel", "kıl payı fark bandı değiştirmemeli"


# --------------------------------------------------------------------------- #
# Eşik altı dersin yeniden deneme penceresi (M1-39)
# --------------------------------------------------------------------------- #


def test_esik_alti_ders_bekleme_suresinden_once_enjekte_edilmez():
    from fusion_cli.memory.lesson_scoring import LESSON_REVIVE_AFTER_S

    lesson = _lesson("zayif modelin sustugu ders", confidence=0.2)

    assert not is_injectable(lesson)
    assert not is_injectable(lesson, idle_s=LESSON_REVIVE_AFTER_S - 1)


def test_esik_alti_ders_bekleme_suresi_dolunca_yeniden_denenir():
    """Ölçüldü (29 Ekim): eşik altı ders bir daha asla ödüllenmiyordu, kalıcı ölüydü."""
    from fusion_cli.memory.lesson_scoring import LESSON_REVIVE_AFTER_S

    lesson = _lesson("zayif modelin sustugu ders", confidence=0.2)

    assert is_injectable(lesson, idle_s=LESSON_REVIVE_AFTER_S)


def test_secim_bekleme_suresi_dolan_esik_alti_dersi_adaya_alir():
    from fusion_cli.memory.lesson_ranking import Candidate, select_lessons
    from fusion_cli.memory.lesson_scoring import LESSON_REVIVE_AFTER_S

    lesson = _lesson("ikinci sans", confidence=0.2)

    assert select_lessons((Candidate(lesson=lesson, distance=0.1),), limit=3) == ()
    taze = Candidate(lesson=lesson, distance=0.1, idle_s=LESSON_REVIVE_AFTER_S)
    assert select_lessons((taze,), limit=3) == (lesson,)


# --------------------------------------------------------------------------- #
# Çelişen eski dersin güveni düşer (A2-11)
# --------------------------------------------------------------------------- #


def test_celisen_eski_ders_dusurulecekler_arasinda():
    eski = _lesson("multi_edit araci kullan")
    ilgisiz = _lesson("testi calistirmadan once bagimliliklari kur")

    assert learning.contradicted_texts(
        (_lesson("multi_edit araci kullanma"),), (eski, ilgisiz)
    ) == (eski.text,)


def test_celisme_yoksa_hicbir_ders_dusurulmez():
    assert learning.contradicted_texts((_lesson("farkli bir konu hakkinda ders"),), ()) == ()


async def test_ogrenme_adimi_celisen_eski_dersin_guvenini_dusurur(monkeypatch):
    from types import SimpleNamespace

    from fusion_cli.engines.agent import learning_steps

    eski = _lesson("multi_edit araci kullan")
    yeni = _lesson("multi_edit araci kullanma", kind=LessonKind.MISTAKE)
    reinforce_cagrilari: list[tuple[tuple[str, ...], bool]] = []

    class _Bellek:
        def all(self):
            return (eski,)

        def add(self, ders):
            return True

        def reinforce(self, texts, *, success):
            reinforce_cagrilari.append((texts, success))
            return len(texts)

    async def cikar(*args, **kwargs):
        return (yeni,)

    from fusion_cli.core.lesson_runtime import LessonRuntimeContext

    monkeypatch.setattr(learning, "extract_lessons", cikar)
    deps = SimpleNamespace(
        lessons=_Bellek(),
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                lesson_attributed_feedback=False, lesson_conflict_quarantine=False
            )
        ),
        lesson_context=LessonRuntimeContext(),
        publisher=SimpleNamespace(publish=lambda event: None),
        tool_context=None,
        mcp_servers=(),
    )
    monkeypatch.setattr(learning_steps, "lesson_tags", lambda deps: ())

    await learning_steps._extract_and_store(
        "gorev", [Message("tool", "unknown option", tool_call_id="1", ok=False)], deps
    )

    assert reinforce_cagrilari == [((eski.text,), False)]


# Task 10a: kontrollü geri bildirim ve çelişki süzgeci.
@pytest.mark.parametrize("origin", ["provider", "infrastructure"])
def test_foundation_kesinti_dogru_dersi_cezalandirmaz(origin):
    from fusion_cli.core.repair_ledger import FailureOrigin

    lesson = _lesson("önce ölç", confidence=0.6)
    assert reinforced(lesson, success=False, failure_origin=FailureOrigin(origin)) == lesson


def test_foundation_retrieval_basari_kullanim_kaniti_degil():
    lesson = _lesson("önce ölç", confidence=0.6)
    assert reinforced(lesson, success=True, feedback_reason="retrieved") == lesson
    assert (
        reinforced(
            lesson, success=True, feedback_reason="verified_outcome", evidence_refs=("check:1",)
        )
        == lesson
    )
    updated = reinforced(
        lesson,
        success=True,
        feedback_reason="verified_outcome",
        used=True,
        evidence_refs=("check:1",),
        verified_at="2026-11-01T00:00:00Z",
    )
    assert updated.success_count == 1
    assert updated.verified_at == "2026-11-01T00:00:00Z"
    assert updated.evidence_refs == ("check:1",)


@pytest.mark.parametrize("pair", range(20))
def test_foundation_yirmi_cift_tersinir_quarantine_ve_surume_gore_suzulur(pair):
    from dataclasses import replace

    from fusion_cli.core.memory import LessonRecallPolicy

    old = replace(
        _lesson(f"eski {pair}"),
        id=f"old-{pair}",
        subject_key=f"api-{pair}",
        version="1",
        applies_to=("python",),
    )
    new = replace(
        _lesson(f"yeni {pair}"),
        id=f"new-{pair}",
        subject_key=f"api-{pair}",
        version="2",
        applies_to=("python",),
        supersedes=(old.id,),
        verified_at="2026-11-01",
        evidence_refs=(f"check:{pair}",),
    )
    candidates = (Candidate(old, 0.1), Candidate(new, 0.1))
    policy = LessonRecallPolicy(
        subject_key=old.subject_key, version="2", applies_to=("python",), conflict_quarantine=True
    )
    assert select_lessons(candidates, limit=4, policy=policy) == (new,)
    quarantined = replace(new, quarantined=True)
    assert select_lessons((Candidate(quarantined, 0.1),), limit=4, policy=policy) == ()
    assert select_lessons(
        (Candidate(replace(quarantined, quarantined=False), 0.1),), limit=4, policy=policy
    ) == (new,)
    assert old in select_lessons(candidates, limit=4)


def test_foundation_blind_development_ve_bilinmeyen_kaynagi_dislar():
    from dataclasses import replace

    from fusion_cli.core.memory import LessonRecallPolicy

    base = _lesson("önce ölç")
    lessons = tuple(replace(base, source_split=split) for split in ("", "development", "blind"))
    assert select_lessons(
        tuple(Candidate(item, 0.1) for item in lessons),
        limit=4,
        policy=LessonRecallPolicy(source_split="blind"),
    ) == (lessons[-1],)


@pytest.mark.parametrize(
    "metadata",
    [
        {"used": False},
        {"used": None, "evidence_refs": ("check:1",)},
        {
            "feedback_reason": "verified_outcome",
            "used": True,
            "evidence_refs": (" ",),
            "verified_at": "today",
        },
    ],
)
def test_foundation_kismi_attribution_legacy_basarisi_sayilmaz(metadata):
    lesson = _lesson("önce ölç", confidence=0.5)
    assert reinforced(lesson, success=True, **metadata) == lesson


def test_foundation_dogrulanmamis_celiski_kontrollu_recallda_elenir():
    from dataclasses import replace

    from fusion_cli.core.memory import LessonRecallPolicy

    first = replace(_lesson("api eski davranış"), id="first", subject_key="api", version="1")
    second = replace(first, id="second", text="api çelişik davranış", version="2")
    candidates = (Candidate(first, 0.1), Candidate(second, 0.1))
    assert (
        select_lessons(candidates, limit=4, policy=LessonRecallPolicy(conflict_quarantine=True))
        == ()
    )
    assert len(select_lessons(candidates, limit=4)) == 2
