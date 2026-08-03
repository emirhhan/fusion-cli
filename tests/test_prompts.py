"""System prompt davranış regression testleri.

Prompt metni ürün davranışıdır: belirli güvenceler kaybolursa agent sessizce
kötüleşir (test çalıştırmadan "bitti" der, dosya okumadan değiştirir, plan modunda
mutasyon yapar). Bu testler o güvenceleri metinde kilitler — birebir cümleyi değil,
DAVRANIŞSAL anahtarı arar; prompt yeniden yazılabilir ama güvence kalmalıdır.
"""

from __future__ import annotations

from fusion_cli.engines.agent.loop import (
    PLAN_MODE_PROMPT,
    SYSTEM_PROMPT,
    _initial_messages,
)


def _system_of(messages):
    assert messages[0].role == "system"
    return messages[0].content


def test_prompt_duzenlemeden_once_okumayi_dayatir():
    assert "oku" in SYSTEM_PROMPT.lower()
    assert "kör değişiklik" in SYSTEM_PROMPT.lower()


def test_prompt_dogrulamayi_dayatir():
    metin = SYSTEM_PROMPT.lower()
    assert "doğrula" in metin
    assert "test" in metin


def test_prompt_uydurmayi_yasaklar():
    assert "uydurma" in SYSTEM_PROMPT.lower()


def test_prompt_arac_cagirmadan_durmayi_yasaklar():
    # "araç çağırmadan durma" — sadece açıklayıp bırakmasın.
    assert "araç çağırmadan durma" in SYSTEM_PROMPT.lower()


def test_prompt_yikici_komutta_durmayi_dayatir():
    metin = SYSTEM_PROMPT.lower()
    assert "rm -rf" in metin or "geri alınamaz" in metin


def test_prompt_paralel_arac_cagrimayi_tesvik_eder():
    # Bağımsız araçları tek tek beklemek turu yavaşlatır; paralel çağırma güvencesi.
    assert "paralel" in SYSTEM_PROMPT.lower()


def test_prompt_arac_adini_kullaniciya_soylemeyi_yasaklar():
    # Kullanıcı araçları değil yapılan işi görmeli ("edit_file çalıştıracağım" dememeli).
    assert "araçların adını" in SYSTEM_PROMPT.lower()


def test_prompt_kutuphane_varligini_dogrulatir():
    # Var olmayan bir kütüphaneyi kullanmak en sık agent hatası; varsaymayı yasaklar.
    metin = SYSTEM_PROMPT.lower()
    assert "varsayma" in metin


def test_prompt_tahmin_yerine_baglam_toplatir():
    # Yol/imza/API tahmin etmek yerine araçla doğrulama güvencesi.
    assert "tahmin etme" in SYSTEM_PROMPT.lower()


def test_ilk_mesaj_daima_system():
    messages = _initial_messages("görev", None, plan_mode=False, extra_system="")
    assert messages[0].role == "system"
    assert messages[-1].role == "user"
    assert messages[-1].content == "görev"


def test_plan_modunda_mutasyon_yasagi_prompta_eklenir():
    messages = _initial_messages("görev", None, plan_mode=True, extra_system="")
    system = _system_of(messages)
    assert "değişiklik yapamazsın" in system.lower()
    assert PLAN_MODE_PROMPT.strip() in system


def test_plan_modu_kapaliyken_mutasyon_yasagi_eklenmez():
    messages = _initial_messages("görev", None, plan_mode=False, extra_system="")
    assert "plan_modu" not in _system_of(messages).lower()


def test_extra_system_promta_eklenir():
    # Ders/uzmanlık bloğu sistem promptuna katılır (compaction'da kaybolmasın).
    messages = _initial_messages("görev", None, plan_mode=False, extra_system="DERS: X yapma.")
    assert "DERS: X yapma." in _system_of(messages)


def test_gecmis_system_ile_gorev_arasinda_korunur():
    from fusion_cli.core.types import Message

    gecmis = [Message("user", "eski"), Message("assistant", "cevap")]
    messages = _initial_messages("yeni", gecmis, plan_mode=False, extra_system="")
    assert messages[1:3] == gecmis
    assert messages[-1].content == "yeni"
