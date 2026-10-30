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


def test_kesik_arac_cagrisi_govdesi_kullaniciya_kalmaz() -> None:
    """Kapanış işareti hiç gelmeyen blok: gövde JSON'u görünür kalmamalı (C1-35)."""
    metin = (
        'Dosyayı yazıyorum.\n\nFUSION_TOOL_CALL\n{"name":"write_file","arguments":{"path":"a.py"'
    )
    sonuc = strip_harness_leaks(metin)
    assert sonuc == "Dosyayı yazıyorum."


def test_payload_ve_eski_bicim_bloklari_ayiklanir() -> None:
    """FUSION_PAYLOAD ve eski <tool_call> blokları da sızmaz (C1-35)."""
    metin = (
        "Başlıyorum.\n\n"
        'FUSION_PAYLOAD id="p1"\n```python\nprint(1)\n```\nFUSION_PAYLOAD_END\n\n'
        '<tool_call>{"name":"x","arguments":{}}</tool_call>\n\nBitti.'
    )
    sonuc = strip_harness_leaks(metin)
    assert "FUSION_PAYLOAD" not in sonuc and "print(1)" not in sonuc
    assert "<tool_call>" not in sonuc
    assert "Başlıyorum." in sonuc and "Bitti." in sonuc


def test_kesik_payload_blogu_sona_kadar_kesilir() -> None:
    sonuc = strip_harness_leaks('Not.\n\nFUSION_PAYLOAD id="p1"\n```py\nprint(1)')
    assert sonuc == "Not."
