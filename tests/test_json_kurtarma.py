"""Zayıf modelin yaygın JSON sapmaları bir MODEL ÇAĞRISI harcamadan düzeltilir.

Ayrıştırıcı sınırlayıcı biçimine karşı zaten toleranslı (fence içine sarılmış
blok, sentinel'siz payload, eski `<tool_call>` biçimi). JSON gövdesi ise katıydı:
düz `json.loads` çağrılıyor ve tek bir fazla virgül turu düşürüyordu.

Bedeli somut: bozuk çağrı sözleşme onarımı tetikliyor, bu da modele yeni bir
mesaj göndermek demek — tarayıcı turunda ~40 saniye. Sıfır maliyetle
düzeltilebilecek bir virgül için bir tur yakmak, kalan onarım hakkını da
tüketiyor (`MAX_TOOL_CONTRACT_REPAIRS`).

Buradaki kurtarmaların hepsi ANLAMI DEĞİŞTİRMEZ; yalnızca sözdizimini onarır.
Belirsiz bir şey varsa kurtarma denenmez ve hata olduğu gibi kalır.
"""

from __future__ import annotations

import json

from fusion_cli.core.tool_emulation import parse_tool_calls


def _tek_cagri(metin: str):
    sonuc = parse_tool_calls(metin)
    return sonuc.calls


def test_sondaki_virgul_kurtarilir() -> None:
    metin = 'FUSION_TOOL_CALL{"name":"read_file","arguments":{"path":"a.py",},}FUSION_TOOL_CALL_END'

    cagrilar = _tek_cagri(metin)

    assert len(cagrilar) == 1
    assert cagrilar[0].name == "read_file"
    assert json.loads(cagrilar[0].arguments) == {"path": "a.py"}


def test_kalin_isaretleme_kurtarilir() -> None:
    """Model sınırlayıcıyı markdown'da kalınlaştırıyor: `**FUSION_TOOL_CALL**`."""
    metin = (
        '**FUSION_TOOL_CALL**{"name":"read_file","arguments":{"path":"a.py"}}'
        "**FUSION_TOOL_CALL_END**"
    )

    cagrilar = _tek_cagri(metin)

    assert len(cagrilar) == 1
    assert json.loads(cagrilar[0].arguments) == {"path": "a.py"}


def test_takma_alan_adlari_kabul_edilir() -> None:
    """`tool`/`parameters` adlandırması diğer sağlayıcıların şemasından geliyor."""
    metin = 'FUSION_TOOL_CALL{"tool":"read_file","parameters":{"path":"a.py"}}FUSION_TOOL_CALL_END'

    cagrilar = _tek_cagri(metin)

    assert len(cagrilar) == 1
    assert cagrilar[0].name == "read_file"
    assert json.loads(cagrilar[0].arguments) == {"path": "a.py"}


def test_arguments_string_olarak_gomulmusse_acilir() -> None:
    metin = (
        'FUSION_TOOL_CALL{"name":"read_file","arguments":"{\\"path\\":\\"a.py\\"}"}'
        "FUSION_TOOL_CALL_END"
    )

    cagrilar = _tek_cagri(metin)

    assert len(cagrilar) == 1
    assert json.loads(cagrilar[0].arguments) == {"path": "a.py"}


def test_kanonik_bicim_bozulmadi() -> None:
    metin = 'FUSION_TOOL_CALL{"name":"read_file","arguments":{"path":"a.py"}}FUSION_TOOL_CALL_END'

    cagrilar = _tek_cagri(metin)

    assert len(cagrilar) == 1
    assert json.loads(cagrilar[0].arguments) == {"path": "a.py"}


def test_gercekten_bozuk_json_kurtarilmaz() -> None:
    """Kurtarma sözdizimi onarır, anlam UYDURMAZ; belirsizde hata kalır."""
    metin = 'FUSION_TOOL_CALL{"name":"read_file","arguments":{"path"FUSION_TOOL_CALL_END'

    sonuc = parse_tool_calls(metin)

    assert not sonuc.calls
    assert sonuc.errors
