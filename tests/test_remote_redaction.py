"""Uzak olay yükü gizleme: meşru kodu bozmaz, bölünmüş sırrı sızdırmaz (R1-05).

Ölçüldü (29 Ekim): `(token|secret|password|…)\\s*[:=]\\s*\\S+` kalıbı `password = input()` gibi
meşru kodu `[gizlendi]` yapıyor, `max_tokens` anahtarının değeri siliniyor, 0,25 sn'lik
delta'lar parça parça redakte edildiği için bölünmüş sır parçalar hâlinde sızıyordu.
"""

from __future__ import annotations

import pytest

from fusion_cli.remote.redaction import REDACTED, redact_payload, redact_text, split_flushable

MESRU = [
    "password = input()",
    "token = get_token()",
    "secret = os.environ['X']()",
    'parola = getpass.getpass("Parola: ")',
    "max_tokens=4096",
    "the password field is required",
]


@pytest.mark.parametrize("metin", MESRU)
def test_meşru_kod_gizlenmez(metin):
    assert redact_text(metin) == metin


@pytest.mark.parametrize(
    ("metin", "sir"),
    [
        ("OPENAI_API_KEY=abc123DEF456ghi", "abc123DEF456ghi"),
        ('password: "iki kelime sir"', "iki kelime sir"),
        ("token = SENTINELtoken123", "SENTINELtoken123"),
        ("Authorization: Bearer SENTINEL+abc/def==ghijklmnop", "SENTINEL+abc/def"),
        ("sk_live_SENTINEL0123456789abcd", "SENTINEL0123456789"),
        ("ghp_SENTINEL0123456789ABCDEFGHIJKLMNOP", "SENTINEL0123456789"),
        ("github_pat_SENTINEL0123456789ABCDEFGHIJ", "SENTINEL0123456789"),
    ],
)
def test_yuksek_guvenli_kaliplar_gizlenir(metin, sir):
    sonuc = redact_text(metin)

    assert sir not in sonuc
    assert REDACTED in sonuc


def test_max_tokens_anahtari_degerini_korur_access_token_gizlenir():
    sonuc = redact_payload({"max_tokens": 4096, "access_token": "x", "api_key": "y", "n": 1})

    assert sonuc == {"max_tokens": 4096, "access_token": REDACTED, "api_key": REDACTED, "n": 1}


def test_bolunmus_sir_parca_parca_sizmaz():
    ready1, tail = split_flushable("anahtar ghp_SENTINEL01234")
    ready2, tail2 = split_flushable(tail + "56789ABCDEFGHIJKLMNOP bitti")
    kalan = tail2

    toplam = "".join(redact_text(parca) for parca in (ready1, ready2, kalan))
    assert "SENTINEL" not in toplam
    assert "anahtar" in toplam and "bitti" in toplam


def test_bosluksuz_cok_uzun_kuyruk_beklemez():
    ready, tail = split_flushable("a" * 1000)

    assert ready == "a" * 1000 and tail == ""
