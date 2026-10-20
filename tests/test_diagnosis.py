"""Ham hata çıktısı yapılandırılmış tanıya çevrilir.

SWE-Doctor'ın bulgusu: testi çalıştırıp çıktıyı modele vermek yetmiyor; asıl kazanç
çıktının "şüpheli konum + belirti" olarak yapılandırılmasından geliyor.

Ölçüldü (5 Eylül Godot koşusu): elimizde `SCRIPT ERROR: Parse Error ... at:
GDScript::reload (res://player.gd:12)` satırı vardı ve kurtarma turu bunu "şu
dosyanın şu satırındaki şu belirti" hâline getiremediği için model aynı yanlışı
tekrarladı.
"""

from __future__ import annotations

from fusion_cli.core.diagnosis import diagnose

GODOT = (
    "Godot Engine v4.7.1.stable.official\n"
    'SCRIPT ERROR: Parse Error: Identifier "velocity" not declared in the current scope.\n'
    "          at: GDScript::reload (res://player.gd:12)\n"
    'ERROR: Failed to load script "res://player.gd" with error "Parse error".\n'
)

TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/proje/calistir.py", line 7, in <module>\n'
    "    print(port_getir({}))\n"
    '  File "/proje/ayarlar.py", line 4, in port_getir\n'
    '    return yapilandirma["port"]\n'
    "KeyError: 'port'\n"
)

PYTEST = (
    "F                                                              [100%]\n"
    "=================================== FAILURES ===================================\n"
    "____________________________ test_ortalama _____________________________________\n"
    "    def test_ortalama():\n"
    ">       assert ortalama([2, 4, 6]) == 4.0\n"
    "E       assert 2.0 == 4.0\n"
    "tests/test_ortalama.py:5: AssertionError\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_ortalama.py::test_ortalama - assert 2.0 == 4.0\n"
)


def test_godot_parse_hatasi_dosya_ve_satira_baglanir():
    tani = diagnose(GODOT)

    assert tani is not None
    assert tani.path == "res://player.gd"
    assert tani.line == 12
    assert "velocity" in tani.symptom


def test_python_tracebackinde_en_icteki_cerceve_secilir():
    """Kök neden en dıştaki çağrı değil, hatanın gerçekleştiği yerdir."""
    tani = diagnose(TRACEBACK)

    assert tani is not None
    assert tani.path.endswith("ayarlar.py")
    assert tani.line == 4
    assert "KeyError" in tani.symptom


def test_pytest_ciktisinda_dusen_test_bulunur():
    tani = diagnose(PYTEST)

    assert tani is not None
    assert tani.path == "tests/test_ortalama.py"
    assert tani.line == 5
    assert "assert" in tani.symptom.casefold()


def test_tanisiz_cikti_uydurmaz():
    assert diagnose("her sey yolunda\n") is None


def test_tani_tek_satirlik_yonerge_uretir():
    tani = diagnose(GODOT)

    assert tani is not None
    yonerge = tani.as_guidance()
    assert "res://player.gd" in yonerge
    assert "12" in yonerge
    assert "velocity" in yonerge
