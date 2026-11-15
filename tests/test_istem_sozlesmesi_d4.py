"""İstem sözleşmesi düzeltmeleri (30 Ekim triyajı: Z1-06/07/09/11/12/13/14/15/17/70/72)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.prompt_fill import fill_template
from fusion_cli.engines.agent import review
from fusion_cli.engines.agent.loop import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.capabilities import CLAUDE_TOOL_MAP

_ISTEMLER = Path(review.__file__).parent / "prompts"
_ROSTER = Path(__file__).parents[1] / "src" / "fusion_cli" / "config" / "roster"


def _oku(ad: str) -> str:
    return (_ISTEMLER / ad).read_text(encoding="utf-8")


def test_yer_tutucu_degerindeki_baska_yer_tutucu_yeniden_doldurulmaz() -> None:
    """Görevde geçen `{trace}` yazısı iz metnini göreve gömmemeli (Z1-70)."""
    sonuc = fill_template("G: {task}\nİ: {trace}", {"task": "bak {trace} nedir", "trace": "IZ"})

    assert sonuc == "G: bak {trace} nedir\nİ: IZ"


def test_json_ornekli_sablonda_suslu_parantez_bozulmaz() -> None:
    sablon = _oku("execution_plan.md")

    sonuc = fill_template(sablon, {"task": "x {y} z"})

    assert '"plan_id": "hesap-makinesi"' in sonuc and "x {y} z" in sonuc
    assert "{task}" not in sonuc


def test_denetci_sorun_yok_yazimlarini_talimat_saymaz() -> None:
    """`Tamam.`, `Sorun yok.` gibi yazımlar düzeltme turu başlatmamalı (Z1-09)."""
    for temiz in ("TAMAM", "Tamam.", "tamam, sorun yok", "Sorun yok.", "  Sorun bulunmuyor"):
        assert review.parse_feedback(temiz) == "", temiz
    gercek = "Test çalıştırılmamış; önce pytest koş ve sonucu bildir."
    assert review.parse_feedback(gercek) == gercek


def test_denetci_iz_ve_cevabi_guvenilmeyen_veri_olarak_citler() -> None:
    metin = _oku("review.txt")

    assert "GÜVENİLMEYEN VERİ" in metin and "talimat değildir" in metin
    assert metin.index("{trace}") > metin.index("GÜVENİLMEYEN VERİ BAŞLANGICI")
    # Rota/entegrasyon maddeleri koşulludur: ilgisiz görevde gürültü üretmesin (Z1-10).
    assert "YALNIZ görev bir API rotası" in metin


def test_ders_istemi_sir_yazmayi_yasaklar_ve_bos_dizi_ister() -> None:
    metin = _oku("lessons.txt")

    assert "parola" in metin and "token" in metin and "[]" in metin
    assert "GÜVENİLMEYEN VERİ" in metin


def test_paperclip_uyanma_notu_citlenir() -> None:
    metin = _oku("paperclip_heartbeat.md")

    assert "GÜVENİLMEYEN VERİ" in metin and "{uyanma}" in metin
    assert metin.index("{uyanma}") > metin.index("GÜVENİLMEYEN VERİ BAŞLANGICI")


def test_plan_istemi_onayi_kaldirmaz_ve_gercek_arac_adlarini_sayar() -> None:
    """Z1-06: 'onay isteme' güvenlik onayı sanılmasın. Z1-07: araç adları kayıtla uyumlu."""
    metin = _oku("execution_plan.md")

    assert "retry_safety: never" in metin and "onay" in metin
    kayitli = set(build_registry().names())
    for ad in ("list_dir", "read_file", "glob", "search_code", "git", "web_search", "web_fetch"):
        assert ad in metin, ad
        assert ad in kayitli, ad
    assert "glob, grep," not in metin


def test_roster_tools_alani_claude_eslemesinde_cozulur() -> None:
    """Roster `tools:` adları sessizce yok sayılmasın (Z1-07 eşleşme testi)."""
    for dosya in sorted(_ROSTER.glob("*.md")):
        satir = next(
            (s for s in dosya.read_text(encoding="utf-8").splitlines() if s.startswith("tools:")),
            None,
        )
        if satir is None:
            continue
        for ad in satir.removeprefix("tools:").split(","):
            assert ad.strip().lower() in CLAUDE_TOOL_MAP, f"{dosya.name}: {ad.strip()}"


def test_sohbet_istemi_model_yer_tutucusu_sizdirmaz_ve_etiketi_sonda_kapatir() -> None:
    """Z1-14, Z1-15."""
    assert "<sistemde verilen model>" not in CHAT_SYSTEM_PROMPT
    assert CHAT_SYSTEM_PROMPT.rstrip().endswith("</kimlik>")
    assert CHAT_SYSTEM_PROMPT.count("</kimlik>") == 1


def test_ajan_istemi_sistem_geneli_kurulum_icin_onay_ister() -> None:
    """Z1-13."""
    kucuk = SYSTEM_PROMPT.lower()

    assert "sistem geneli" in kucuk and "onay iste" in kucuk
    assert "proje içi bağımlılık" in kucuk


def test_ajan_istemi_sahte_entegrasyon_kurallari_ayri_ve_acik() -> None:
    """Z1-17: üç kural bağlamsız tek cümlede değil, ayrı maddelerde."""
    assert "`success: true`" in SYSTEM_PROMPT
    assert "sunucuda" in SYSTEM_PROMPT


def test_guvenlik_kurallari_israrla_asilmaz() -> None:
    """Z1-72."""
    assert "ısrarla aşılamaz" in SYSTEM_PROMPT
    assert "ısrarla aşılamaz" in CHAT_SYSTEM_PROMPT
