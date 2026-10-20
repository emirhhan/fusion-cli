"""Çerçeve metinleri kullanıcıya ve kalıcı sohbete sızmamalı."""

from fusion_cli.core.leak_filter import is_harness_note, strip_harness_leaks

NOT = (
    "[eylem-kanıtı-zorunlu] Kullanıcı gerçek bir işlem istedi.\n"
    'FUSION_TOOL_CALL\n```json\n{"name":"run_shell"}\n```\nFUSION_TOOL_CALL_END\n'
    "yapılmış gibi davranma."
)


def test_arac_cagrisi_cercevesi_ve_yetim_isaret_silinir() -> None:
    blok = 'FUSION_TOOL_CALL\n{"name":"x"}\nFUSION_TOOL_CALL_END'
    metin = f"Tamam, bitti.\n\n{blok}\n\nSon.\nFUSION_TOOL_CALL_END"
    sonuc = strip_harness_leaks(metin)
    assert "FUSION_TOOL_CALL" not in sonuc
    assert "Tamam, bitti." in sonuc and "Son." in sonuc


def test_harness_notu_paragrafi_cevaptan_cikar() -> None:
    sonuc = strip_harness_leaks(f"Merhaba\n\n{NOT}\n\nGörüşürüz")
    assert "eylem-kanıtı" not in sonuc and "FUSION_TOOL_CALL" not in sonuc
    assert sonuc.startswith("Merhaba") and sonuc.endswith("Görüşürüz")


def test_harness_notu_kullanici_mesaji_sayilir() -> None:
    assert is_harness_note(NOT) and not is_harness_note("Siteyi güncelle")


def test_normal_metin_degismez() -> None:
    assert strip_harness_leaks("Normal cevap.\n\n- madde") == "Normal cevap.\n\n- madde"
