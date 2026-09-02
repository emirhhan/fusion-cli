"""Sır redaksiyonu: metin maskeleme + çıkış noktalarına (JSONL, sağlayıcı hatası) uygulanışı."""

from __future__ import annotations

import io

from fusion_cli.core.events import ModelCallFinished
from fusion_cli.core.redaction import REDACTED_MARK, redact
from fusion_cli.core.types import ModelResult
from fusion_cli.observability.json_sink import JsonRenderer


def test_redact_api_anahtarini_maskeler():
    cikti = redact("anahtar sk-ABCDEFGH1234567890 burada")

    assert "sk-ABCDEFGH1234567890" not in cikti
    assert REDACTED_MARK in cikti


def test_redact_bearer_token_maskeler():
    assert "Bearer abcdef123456xyz" not in redact("Authorization: Bearer abcdef123456xyz")


def test_redact_kisa_json_yaml_ve_key_value_sirlarini_maskeler():
    degerler = ("qx1", "qy2", "qz3")
    cikti = redact(
        'credentials: "qx1"\napi_key=qy2\nAuthorization: Bearer qz3'
    )

    assert all(deger not in cikti for deger in degerler)
    assert REDACTED_MARK in cikti


def test_redact_temiz_metni_degistirmez():
    assert redact("sıradan bir açıklama") == "sıradan bir açıklama"
    assert redact("author: bob") == "author: bob"


def test_redact_birden_fazla_eslesmeyi_maskeler():
    cikti = redact("sk-AAAAAAAAAAAAAAAA ve sk-BBBBBBBBBBBBBBBB")

    assert "sk-AAAA" not in cikti and "sk-BBBB" not in cikti


def test_json_sink_sirri_yazmaz():
    tampon = io.StringIO()
    renderer = JsonRenderer(stream=tampon)

    renderer.handle(
        ModelCallFinished(
            role="agent",
            result=ModelResult(
                name="agent",
                model="x",
                text="",
                latency_ms=1,
                ok=False,
                error="AuthError: Bearer sk-GIZLIANAHTAR1234567 reddedildi",
            ),
        )
    )

    yazilan = tampon.getvalue()
    assert "sk-GIZLIANAHTAR1234567" not in yazilan
    assert REDACTED_MARK in yazilan
