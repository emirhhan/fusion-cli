"""Tanı/denetim çıktısı sentetik sır fixture'larını dışarı taşımamalı (WP20 madde 1).

Python tarafındaki tek merkezi gizleyici `core.redaction.redact`; JSONL akışı ve
denetim kaydı bunun üstünden geçer. Sızıntı yoksa değer YOKTUR: her fixture'ın
sır kısmı çıktıda aranır, çevresindeki tanı bilgisi (anahtar adı, host) korunmalı.
Arayüz tarafındaki aynı sözleşme `app/src/feedback/report.test.ts` içindedir.
"""

from __future__ import annotations

import io
import json

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.redaction import REDACTED_MARK, redact
from fusion_cli.observability.json_sink import JsonRenderer

# (ad, girdi, çıktıda ASLA bulunmaması gereken sır)
SENTETIK_SIRLAR = [
    ("openai", "anahtar sk-proj-SENTINEL1234567890abcdef kullan", "SENTINEL1234567890abcdef"),
    ("github-ghp", "tok ghp_SENTINEL0123456789ABCDEFGHIJKLMNOP bitti", "SENTINEL0123456789"),
    ("github-gho", "tok gho_SENTINEL0123456789ABCDEFGHIJKLMNOP", "SENTINEL0123456789"),
    (
        "github-ince",
        "github_pat_11SENTINEL0abcdefghijkl_ABCDEFGHIJKLMNOPQRSTUV",
        "SENTINEL0abcdefghijkl",
    ),
    (
        "pem",
        "-----BEGIN PRIVATE KEY-----\nSENTINELPEMBODY\n-----END PRIVATE KEY-----",
        "SENTINELPEMBODY",
    ),
    (
        "pem-kesik",
        "-----BEGIN RSA PRIVATE KEY-----\nSENTINELPEMBODY",
        "SENTINELPEMBODY",
    ),
    ("bearer", "Authorization: Bearer SENTINEL.bearer-123_xyz", "SENTINEL.bearer-123_xyz"),
    ("basic", "Authorization: Basic U0VOVElORUw6cGFzcw==", "U0VOVElORUw6cGFzcw"),
    ("url-parola", "git clone https://deploy:SENTINELPW@git.example.com/r.git", "SENTINELPW"),
    ("url-parola-yerel", "http://admin:SENTINELPW@localhost:8080/x", "SENTINELPW"),
    ("url-parola-ip", "redis://:SENTINELPW@10.0.0.5:6379/0", "SENTINELPW"),
    ("url-parola-ssh", "ssh://git:SENTINELPW@host/r", "SENTINELPW"),
    ("nim-env", "NVIDIA_NIM_API_KEY=nvapi-SENTINELNIMKEY12345", "SENTINELNIMKEY12345"),
    ("nim-kisa", "export NVIDIA_NIM_API_KEY=SENTINELshort", "SENTINELshort"),
    ("json-parola", '{"password": "SENTINELJSONPW"}', "SENTINELJSONPW"),
    ("tirnakli-bosluklu", '{"password": "SENTINEL TWO WORDS"}', "TWO WORDS"),
    ("env-tirnakli", "OPENAI_API_KEY='SENTINEL SPACED'", "SPACED"),
    ("aws", "AKIASENTINEL12345678", "SENTINEL"),
    ("slack", "xoxb-1234567890-SENTINELslack", "SENTINELslack"),
    ("url-imza", "https://cdn.example.com/a?sig=SENTINELSIG&x=1", "SENTINELSIG"),
    ("stripe-canli", "odeme sk_live_SENTINEL0123456789abcdef kullan", "SENTINEL0123456789"),
    ("stripe-test", "rk_test_SENTINEL0123456789abcdef", "SENTINEL0123456789"),
    (
        "jwt",
        "oturum eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJTRU5USU5FTCJ9.SENTINELsig0123456789 bitti",
        "SENTINELsig0123456789",
    ),
    ("bearer-base64", "Authorization: Bearer SENTINEL+abc/def==", "abc/def=="),
]


@pytest.mark.parametrize(
    ("girdi", "sir"),
    [(g, s) for _, g, s in SENTETIK_SIRLAR],
    ids=[ad for ad, _, _ in SENTETIK_SIRLAR],
)
def test_redact_sentetik_sirri_cikarmaz(girdi: str, sir: str) -> None:
    sonuc = redact(girdi)
    assert sir not in sonuc
    assert REDACTED_MARK in sonuc


def test_redact_tani_baglamini_korur() -> None:
    sonuc = redact("host=db.internal durum=hazir password=SENTINELPW")
    assert "host=db.internal" in sonuc
    assert "durum=hazir" in sonuc
    assert "SENTINELPW" not in sonuc


def test_url_parolasi_host_bilgisini_siler_ama_yolu_korur() -> None:
    sonuc = redact("http://admin:SENTINELPW@localhost:8080/api/v1")
    assert "localhost:8080/api/v1" in sonuc


def test_jsonl_akisi_sentetik_sirlari_yazmaz() -> None:
    """Olay → JSONL: araç argümanı ve çıktısındaki her sır akıştan önce gizlenir."""
    akis = io.StringIO()
    for ad, girdi, _sir in SENTETIK_SIRLAR:
        JsonRenderer(akis).handle(
            ToolExecuted(
                name="bash",
                args={"komut": girdi, "ad": ad},
                outcome=ToolOutcome.OK,
                output=girdi,
            )
        )
    yazilan = akis.getvalue()
    for _, _, sir in SENTETIK_SIRLAR:
        assert sir not in yazilan
    for satir in yazilan.splitlines():
        json.loads(satir)  # gizleme JSON'u bozmamalı
