"""Hızlı başlayan görevin çalışma kanıtıyla profesyonel akışa yükselmesi."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolFamily, tool_family
from fusion_cli.engines.agent.promotion import (
    ExecutionSignals,
    PromotionContext,
    ToolUse,
    TurnObservation,
    should_promote,
    signals_from_turn,
)


@pytest.mark.parametrize(
    ("signals", "reason"),
    [
        (ExecutionSignals(pending_todos=3), "üç veya daha fazla bekleyen iş"),
        (ExecutionSignals(touched_components=2), "birden fazla bileşen"),
        (ExecutionSignals(tool_families=2), "birden fazla araç ailesi"),
        (ExecutionSignals(has_dependency=True), "araç çıktısına bağlı sonraki iş"),
        (ExecutionSignals(needs_repair=True), "teşhis ve onarım gerektiren hata"),
        (ExecutionSignals(needs_verification=True), "ayrı doğrulama gereksinimi"),
        (ExecutionSignals(budget_pressure=True), "hızlı yol bütçesi yetersiz"),
    ],
)
def test_karmaşıklık_sinyali_workflowa_yukseltir(signals, reason):
    decision = should_promote(signals)

    assert decision.should_promote is True
    assert decision.reasons == (reason,)


def test_sinyal_yoksa_hizli_yol_devam_eder():
    decision = should_promote(ExecutionSignals())

    assert decision.should_promote is False
    assert decision.reasons == ()


def test_birden_fazla_sinyal_tum_gerekceleri_kararli_sirada_tasir():
    decision = should_promote(ExecutionSignals(pending_todos=4, tool_families=2, needs_repair=True))

    assert decision.reasons == (
        "üç veya daha fazla bekleyen iş",
        "birden fazla araç ailesi",
        "teşhis ve onarım gerektiren hata",
    )


# --------------------------------------------------------------------------- #
# Araç aileleri
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "family"),
    [
        ("write_file", ToolFamily.FILES),
        ("scaffold_web", ToolFamily.FILES),
        ("grep_search", ToolFamily.SEARCH),
        ("run_shell", ToolFamily.SHELL),
        ("git", ToolFamily.VCS),
        ("browser_click", ToolFamily.BROWSER),
        ("web_search", ToolFamily.WEB),
        ("spawn_agent", ToolFamily.DELEGATION),
        ("invoke_subagent", ToolFamily.DELEGATION),
        ("todo_write", ToolFamily.META),
        ("ask_user", ToolFamily.META),
        ("find_skill", ToolFamily.META),
    ],
)
def test_arac_adi_is_ailesine_cevrilir(name, family):
    assert tool_family(name) is family


def test_mcp_araci_dis_aile_sayilir():
    assert tool_family("novamira__list_products") is ToolFamily.EXTERNAL


def test_bilinmeyen_arac_dis_aile_sayilir():
    """Tanımadığımız araç eklenti/dış kaynaklıdır; yardımcı sayılıp gizlenmemeli."""
    assert tool_family("hic_gorulmemis_arac") is ToolFamily.EXTERNAL


# --------------------------------------------------------------------------- #
# Tur kanıtından sinyal çıkarımı
# --------------------------------------------------------------------------- #


def test_bekleyen_todo_sayisi_sinyale_tasinir():
    signals = signals_from_turn(TurnObservation(pending_todos=4))

    assert signals.pending_todos == 4


def test_ayni_dosyaya_birden_cok_dokunus_tek_bilesen_sayilir():
    observation = TurnObservation(touched_paths=("src/a.py", "src/a.py"))

    assert signals_from_turn(observation).touched_components == 1


def test_ikinci_dosya_ikinci_bilesen_sayilir():
    observation = TurnObservation(touched_paths=("src/a.py", "src/b.py"))

    assert signals_from_turn(observation).touched_components == 2


def test_yardimci_araclar_aile_sayisini_sismez():
    """`todo_write` ve `ask_user` iş üretmez; karmaşıklık kanıtı sayılmamalı."""
    observation = TurnObservation(
        tool_uses=(ToolUse("read_file"), ToolUse("todo_write"), ToolUse("ask_user"))
    )

    assert signals_from_turn(observation).tool_families == 1


def test_farkli_is_aileleri_ayri_sayilir():
    observation = TurnObservation(tool_uses=(ToolUse("read_file"), ToolUse("run_shell")))

    assert signals_from_turn(observation).tool_families == 2


def test_okunan_ciktidan_sonra_gelen_degistirici_cagri_bagimlilik_sayilir():
    observation = TurnObservation(
        tool_uses=(ToolUse("read_file"), ToolUse("write_file", mutating=True))
    )

    assert signals_from_turn(observation).has_dependency is True


def test_okumadan_yapilan_degisiklik_bagimlilik_sayilmaz():
    observation = TurnObservation(tool_uses=(ToolUse("write_file", mutating=True),))

    assert signals_from_turn(observation).has_dependency is False


def test_basarisiz_okuma_bagimlilik_zinciri_kurmaz():
    """Çıktı üretmeyen bir okuma, sonraki değişikliğin girdisi olamaz."""
    observation = TurnObservation(
        tool_uses=(ToolUse("read_file", ok=False), ToolUse("write_file", mutating=True))
    )

    assert signals_from_turn(observation).has_dependency is False


def test_dusen_arac_cagrisi_onarim_sinyali_uretir():
    observation = TurnObservation(tool_uses=(ToolUse("read_file", ok=False),))

    assert signals_from_turn(observation).needs_repair is True


def test_calisan_komut_ayri_dogrulama_gerektirir():
    """Kabuk/VCS etkisi modelin sözüyle değil, ayrı kanıtla doğrulanmalıdır."""
    observation = TurnObservation(tool_uses=(ToolUse("run_shell", mutating=True),))

    assert signals_from_turn(observation).needs_verification is True


def test_salt_okuma_turu_dogrulama_gereksinimi_uretmez():
    observation = TurnObservation(tool_uses=(ToolUse("read_file"), ToolUse("grep_search")))

    assert signals_from_turn(observation).needs_verification is False


@pytest.mark.parametrize(
    "observation",
    [
        TurnObservation(hit_step_limit=True),
        TurnObservation(budget_stopped=True),
    ],
)
def test_tukenen_butce_baski_sinyali_uretir(observation):
    assert signals_from_turn(observation).budget_pressure is True


def test_bos_tur_hicbir_sinyal_uretmez():
    assert signals_from_turn(TurnObservation()) == ExecutionSignals()


# --------------------------------------------------------------------------- #
# Yükseltme bağlamı
# --------------------------------------------------------------------------- #


def test_yukseltme_baglami_kanitlari_okunabilir_blokta_toplar():
    context = PromotionContext(
        task_summary="dosyaları düzelt",
        reasons=("teşhis ve onarım gerektiren hata",),
        touched_paths=("src/a.py",),
        pending_todos=("testleri çalıştır",),
        tool_evidence=("read_file: başarısız",),
    )

    rendered = context.render()

    assert "dosyaları düzelt" in rendered
    assert "teşhis ve onarım gerektiren hata" in rendered
    assert "src/a.py" in rendered
    assert "testleri çalıştır" in rendered
    assert "read_file: başarısız" in rendered


def test_yukseltme_baglami_ham_gecmis_tasimaz():
    """Tasarım gereği mesaj geçmişi kopyalanmaz; yalnız tipli kanıt taşınır."""
    context = PromotionContext(task_summary="iş", reasons=("birden fazla bileşen",))

    rendered = context.render()

    assert "Yok" in rendered
    assert len(rendered.splitlines()) <= 12


def test_yukseltme_baglami_kanit_listelerini_sinirlar():
    """Plan istemi sınırsız büyümemeli; kanıt listeleri kırpılır."""
    context = PromotionContext(
        task_summary="iş",
        reasons=("birden fazla bileşen",),
        touched_paths=tuple(f"src/f{index}.py" for index in range(50)),
    )

    rendered = context.render()

    assert "src/f0.py" in rendered
    assert "src/f49.py" not in rendered
