"""Sır redaksiyonu: metin maskeleme + çıkış noktalarına (JSONL, sağlayıcı hatası) uygulanışı."""

from __future__ import annotations

import io

import pytest

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
    cikti = redact('credentials: "qx1"\napi_key=qy2\nAuthorization: Bearer qz3')

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


def test_openrouter_ve_nim_anahtar_bicimleri_maskelenir():
    from fusion_cli.core.redaction import redact

    metin = "or=sk-or-v1-0123456789abcdef0123 nim=nvapi-AbCdEf0123456789_xyz"
    temiz = redact(metin)
    assert "sk-or-v1-0123" not in temiz
    assert "nvapi-AbCdEf" not in temiz


@pytest.mark.parametrize(
    "secret", ["passwd=synthetic_value", "access_key=synthetic_value", "AIza" + "a" * 32]
)
def test_redact_fast_path_cannot_skip_known_secret_patterns(secret):
    assert redact(secret) == REDACTED_MARK


def test_akis_gizleyicisi_parca_sinirindaki_sirri_yakalar():
    from fusion_cli.core.redaction import StreamRedactor

    gizleyici = StreamRedactor()
    cikti = [gizleyici.feed("a ghp_SENTINEL01234"), gizleyici.feed("56789ABCDEFGHIJKLMNOP b\n")]
    cikti.append(gizleyici.flush())

    assert "SENTINEL" not in "".join(cikti)
    assert "".join(cikti).startswith("a ")


def test_akis_gizleyicisi_kapanmamis_pem_blogunu_bitene_dek_tutar():
    from fusion_cli.core.redaction import StreamRedactor

    gizleyici = StreamRedactor()
    parcalar = [
        gizleyici.feed("anahtar:\n-----BEGIN PRIVATE KEY-----\nSENTINELBODY1\n"),
        gizleyici.feed("SENTINELBODY2\n-----END PRIVATE KEY-----\nbitti\n"),
        gizleyici.flush(),
    ]

    toplam = "".join(parcalar)
    assert "SENTINELBODY" not in toplam
    assert "bitti" in toplam
    assert "SENTINELBODY" not in parcalar[0]


def test_akis_gizleyicisi_sirsiz_metni_aynen_birlestirir():
    from fusion_cli.core.redaction import StreamRedactor

    gizleyici = StreamRedactor()
    parcalar = ["merhaba ", "dünya\n", "ikinci ", "satır"]
    toplam = "".join(gizleyici.feed(p) for p in parcalar) + gizleyici.flush()

    assert toplam == "merhaba dünya\nikinci satır"


def test_uzun_bosluksuz_govde_redaksiyonu_karesel_yavaslatmaz():
    """Ölçüldü (30 Ekim): anahtar=değer deseninin sınırsız önek/soneki uzun boşluksuz gövdede
    karesel çalışıyordu (3 200 karakter 1,3 sn; 50 000 karakter dakikalar). Önek/sonek 64 ile
    sınırlandı; sır yine maskelenir."""
    import time

    from fusion_cli.core.redaction import redact

    metin = (
        "Authorization: Bearer abcdef1234567890xyz\n" + "x" * 50_000 + " ANTHROPIC_API_KEY=sk-gizli"
    )
    baslangic = time.monotonic()

    sonuc = redact(metin)

    assert time.monotonic() - baslangic < 5
    assert "abcdef1234567890xyz" not in sonuc and "sk-gizli" not in sonuc
