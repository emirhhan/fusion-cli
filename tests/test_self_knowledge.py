"""Her modele Fusion'ın kendisi anlatılır; elde olmayan yetenek varmış gibi sunulmaz."""

from fusion_cli.engines.agent.self_knowledge import GUIDE, knowledge_block, session_line


def test_kilavuz_ana_yuzeyleri_ve_zeka_katmanini_anlatir() -> None:
    for kelime in (
        "Chrome eklentisi",
        "Fusion Browser",
        "browser_mirror",
        "Kits",
        "ask_teacher",
        "council",
        "recall_lessons",
        "Kontrol Paneli",
        "Dürüstlük",
    ):
        assert kelime in GUIDE


def test_kilavuz_bagiam_butcesini_asmaz() -> None:
    assert len(GUIDE) <= 4_200


def test_dinamik_satir_yalniz_sunulan_aileleri_sayar() -> None:
    satir = session_line(["read_file", "run_shell", "browser_open", "ask_teacher"], "gemini_web/x")
    assert "Fusion Browser" in satir and "öğretmen" in satir
    assert "Öğretmen: gemini_web/x" in satir
    assert "Chrome eklentisi (gerçek Chrome)" in satir.split("KAPALI olanlar:")[1]


def test_blok_kilavuz_ve_satiri_birlestirir() -> None:
    blok = knowledge_block(["read_file", "chrome_page"])
    assert blok.startswith(GUIDE) and "Chrome eklentisi (gerçek Chrome)" in blok
