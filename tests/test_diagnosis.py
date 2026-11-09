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


NODE_HATASI = (
    "/proje/app.js:12\n"
    "    const x = ;\n"
    "              ^\n\n"
    "SyntaxError: Unexpected token ';'\n"
    "    at wrapSafe (node:internal/modules/cjs/loader:1281:20)\n"
)


def test_node_yigin_izi_tani_uretir():
    tani = diagnose(NODE_HATASI)

    assert tani is not None
    assert (tani.path, tani.line) == ("/proje/app.js", 12)
    assert "SyntaxError" in tani.symptom


def test_grep_ciktisi_calisma_zamani_hatasi_sanilmaz():
    """`grep -n` satırı (`dosya.js:12:metin`) tanı değildir (C1-32)."""
    assert diagnose("src/app.js:12:const x = 1;\nsrc/b.js:3:let y;\n") is None


def test_hata_belirtisi_olmayan_dosya_satir_cifti_tani_degildir():
    assert diagnose("/proje/app.js:12\n    kod\n") is None


EXCEPTION_GROUP = (
    "  + Exception Group Traceback (most recent call last):\n"
    '  |   File "/project/cleanup.py", line 90, in close\n'
    "  | ExceptionGroup: cleanup failures (1 sub-exception)\n"
    "  +-+---------------- 1 ----------------\n"
    "    | Traceback (most recent call last):\n"
    '    |   File "/project/wrapper.py", line 99, in report\n'
    "    | RuntimeError: cleanup did not finish\n"
    "    +------------------------------------\n"
)


def test_group_cleanup_frames_cannot_steal_plain_primary_exception():
    diagnosis = diagnose(TRACEBACK + "\n" + EXCEPTION_GROUP)
    assert diagnosis is not None
    assert (diagnosis.path, diagnosis.line, diagnosis.symptom) == (
        "/proje/ayarlar.py",
        4,
        "KeyError: 'port'",
    )
    assert "wrapper" not in diagnosis.quote


def test_group_only_trace_is_not_flattened_into_a_confident_root_location():
    assert diagnose(EXCEPTION_GROUP) is None


def test_chaining_uses_frame_and_terminal_exception_from_latest_complete_block():
    diagnosis = diagnose(
        TRACEBACK
        + "\nDuring handling of the above exception, another exception occurred:\n\n"
        + "Traceback (most recent call last):\n"
        + '  File "/project/service.py", line 18, in start\n'
        + "    raise RuntimeError('startup failed')\n"
        + "RuntimeError: startup failed\n"
    )
    assert diagnosis is not None
    assert (diagnosis.path, diagnosis.line, diagnosis.symptom) == (
        "/project/service.py",
        18,
        "RuntimeError: startup failed",
    )


def test_truncated_new_trace_cannot_take_exception_from_previous_complete_trace():
    diagnosis = diagnose(
        TRACEBACK
        + "\nTraceback (most recent call last):\n"
        + '  File "/project/incomplete.py", line 44, in stop\n'
        + "    release_resources()\n"
    )
    assert diagnosis is not None
    assert (diagnosis.path, diagnosis.line, diagnosis.symptom) == (
        "/proje/ayarlar.py",
        4,
        "KeyError: 'port'",
    )


def test_new_header_without_frame_cannot_reuse_old_frame_with_new_exception():
    diagnosis = diagnose(
        TRACEBACK + "\nTraceback (most recent call last):\nValueError: later error\n"
    )
    assert diagnosis is not None
    assert diagnosis.path == "/proje/ayarlar.py"
    assert diagnosis.symptom == "KeyError: 'port'"


def test_exception_line_without_a_new_trace_cannot_replace_completed_symptom():
    diagnosis = diagnose(TRACEBACK + "\nRuntimeError: unrelated summary\n")
    assert diagnosis is not None
    assert diagnosis.symptom == "KeyError: 'port'"


def test_incomplete_trace_before_unrelated_log_cannot_claim_its_later_error():
    assert (
        diagnose(
            "Traceback (most recent call last):\n"
            '  File "/project/incomplete.py", line 44, in stop\n'
            "unrelated service log\n"
            "ValueError: other service failed\n"
        )
        is None
    )


def test_incomplete_trace_without_terminal_exception_does_not_guess_symptom():
    assert (
        diagnose(
            "Traceback (most recent call last):\n"
            '  File "/project/incomplete.py", line 44, in stop\n'
        )
        is None
    )


def test_group_boundary_ends_incomplete_plain_trace_before_unrelated_exception():
    assert (
        diagnose(
            "Traceback (most recent call last):\n"
            '  File "/project/incomplete.py", line 44, in stop\n'
            + EXCEPTION_GROUP
            + "RuntimeError: unrelated summary\n"
        )
        is None
    )


def test_indented_source_quote_is_not_a_traceback_frame():
    diagnosis = diagnose(
        "Traceback (most recent call last):\n"
        '  File "/project/worker.py", line 12, in run\n'
        "    print('File \"/project/not_a_frame.py\", line 999')\n"
        "ValueError: bad input\n"
    )
    assert diagnosis is not None
    assert (diagnosis.path, diagnosis.line) == ("/project/worker.py", 12)


def test_plain_trace_header_must_be_anchored_not_a_log_or_source_quote():
    assert (
        diagnose(
            "INFO quoted Traceback (most recent call last):\n"
            '  File "/project/not_a_frame.py", line 999\n'
            "ValueError: a quoted error\n"
        )
        is None
    )


def test_missing_parseable_inner_frame_is_not_replaced_with_outer_frame():
    assert (
        diagnose(
            "Traceback (most recent call last):\n"
            '  File "/project/outer.py", line 1, in call\n'
            '  File "/project/inner.py", line unknown, in run\n'
            "ValueError: bad input\n"
        )
        is None
    )


def test_bare_base_exception_is_still_associated_with_its_own_trace_block():
    diagnosis = diagnose(
        "Traceback (most recent call last):\n"
        '  File "/project/worker.py", line 12, in run\n'
        "Exception: failed\n"
    )
    assert diagnosis is not None
    assert diagnosis.symptom == "Exception: failed"


def test_plain_completed_trace_after_group_has_its_own_matching_symptom():
    diagnosis = diagnose(
        EXCEPTION_GROUP
        + "Traceback (most recent call last):\n"
        + '  File "/project/final.py", line 24\n'
        + "TypeError: invalid result\n"
    )
    assert diagnosis is not None
    assert (diagnosis.path, diagnosis.line, diagnosis.symptom) == (
        "/project/final.py",
        24,
        "TypeError: invalid result",
    )
