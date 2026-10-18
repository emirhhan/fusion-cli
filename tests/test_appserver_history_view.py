"""Görünür geçmiş araç olaylarını sıralı ve güvenli sunar."""

from __future__ import annotations

from fusion_cli.core.types import Message, ToolCall


def test_arac_olayi_kronolojiyi_ve_gercek_diffi_korur():
    from fusion_cli.appserver.history_view import visible_history

    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-eski\n+yeni"
    messages = [
        Message("user", "yap"),
        Message(
            "assistant", "Yazıyorum", tool_calls=(ToolCall("c", "edit_file", '{"path":"a.py"}'),)
        ),
        Message("tool", "yazıldı", tool_call_id="c", name="edit_file", ok=True, tool_diff=diff),
        Message("assistant", "Bitti", message_id="last"),
    ]
    assert visible_history(messages) == [
        {"rol": "kullanici", "metin": "yap"},
        {"rol": "asistan", "metin": "Yazıyorum", "ara": True},
        {
            "rol": "olay",
            "id": "c",
            "olay": {
                "olay": "ToolExecuted",
                "name": "edit_file",
                "args": {"path": "a.py"},
                "outcome": "ok",
                "output": "yazıldı",
                "diff": diff,
            },
        },
        {"rol": "asistan", "metin": "Bitti", "id": "last"},
    ]
    assert messages[2].content == "yazıldı"


def test_bozuk_arguman_basarisiz_diff_ve_ic_notlar_gizlenir():
    from fusion_cli.appserver.history_view import visible_history

    messages = [
        Message("assistant", "", tool_calls=(ToolCall("c", "edit_file", "["),)),
        Message("tool", "password=ornek", tool_call_id="c", ok=False, tool_diff="diff"),
        Message("user", "iç not", harness_note=True),
        Message("assistant", " "),
    ]
    rows = visible_history(messages)
    assert len(rows) == 1
    event = rows[0]["olay"]
    assert event == {
        "olay": "ToolExecuted",
        "name": "edit_file",
        "args": {},
        "outcome": "failed",
        "output": "[gizlendi]",
        "diff": None,
    }


def test_argumanlar_ve_diff_sirlari_maskelenir():
    from fusion_cli.appserver.history_view import visible_history

    messages = [
        Message(
            "assistant",
            "",
            tool_calls=(
                ToolCall(
                    "c",
                    "write_file",
                    '{"path":"a.py","password":"ornek deger","nested":{"token":"ornek"}}',
                ),
            ),
        ),
        Message("tool", "ok", tool_call_id="c", ok=True, tool_diff="+password=ornek"),
    ]
    event = visible_history(messages)[0]["olay"]
    assert isinstance(event, dict)
    assert "ornek" not in str(event)
    assert event["args"] == {
        "path": "a.py",
        "password": "[gizlendi]",
        "nested": {"token": "[gizlendi]"},
    }


def test_eski_basarili_cikti_diffi_geri_kazanilir_ama_belirsiz_sonuc_sayilmaz():
    from fusion_cli.appserver.history_view import visible_history

    diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-eski\n+yeni"
    rows = visible_history(
        [
            Message("tool", "yazıldı\n" + diff, name="edit_file", ok=True),
            Message("tool", diff),
            Message("tool", diff, ok=False),
        ]
    )
    assert [row["olay"]["diff"] for row in rows] == [diff, None, None]


def test_okunan_patch_dosyasi_degistirilmis_dosya_sayilmaz():
    from fusion_cli.appserver.history_view import visible_history

    patch = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-eski\n+yeni"
    event = visible_history([Message("tool", patch, name="read_file", ok=True)])[0]["olay"]
    assert isinstance(event, dict)
    assert event["diff"] is None


def test_derin_arguman_gecmisi_dusurmeden_bos_nesneye_doner():
    from fusion_cli.appserver.history_view import visible_history

    arguments = '{"nested":' * 600 + '"deger"' + "}" * 600
    messages = [
        Message("assistant", "", tool_calls=(ToolCall("c", "read_file", arguments),)),
        Message("tool", "ok", tool_call_id="c", ok=True),
        Message("assistant", "Bitti"),
    ]
    rows = visible_history(messages)
    event = rows[0]["olay"]
    assert isinstance(event, dict)
    assert event["args"] == {}
    assert rows[1] == {"rol": "asistan", "metin": "Bitti"}
