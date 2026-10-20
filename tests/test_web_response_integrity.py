"""Web yanıtının bütünlüğü tek yerde sınıflandırılır.

Tarayıcı taşımasında kayıp üç ayrı biçimde geliyor ve üçü farklı kurtarma ister:
yanıt hiç gelmemiş (boş), üretim ortasında kesilmiş (yarım blok), ya da model
sözleşmeyi bozmuş. Bunları tek bir "model boş cevap verdi" kutusuna koymak, 5-6
Eylül koşularında turun neden bittiğini görünmez kıldı.
"""

from __future__ import annotations

from fusion_cli.core.tool_emulation import CALL_OPEN as CALL
from fusion_cli.core.tool_emulation import PAYLOAD_OPEN
from fusion_cli.core.web_response import ResponseIntegrity, classify_response


def test_bos_yanit_ayri_sinif():
    assert classify_response("", truncated=False, has_tool_calls=False) is ResponseIntegrity.EMPTY
    assert (
        classify_response("   \n ", truncated=False, has_tool_calls=False)
        is ResponseIntegrity.EMPTY
    )


def test_saglayici_kesmesi_truncated_sayilir():
    sonuc = classify_response("yarım kalan metin", truncated=True, has_tool_calls=False)

    assert sonuc is ResponseIntegrity.TRUNCATED


def test_kapanmamis_cagri_blogu_ayri_sinif():
    metin = f'Şunu yapıyorum. {CALL}{{"name":"read_file","arguments":'

    sonuc = classify_response(metin, truncated=False, has_tool_calls=False)

    assert sonuc is ResponseIntegrity.UNCLOSED_BLOCK


def test_kapanmamis_payload_blogu_ayri_sinif():
    metin = f'{PAYLOAD_OPEN} id="a"\nkod satiri\n'

    sonuc = classify_response(metin, truncated=False, has_tool_calls=False)

    assert sonuc is ResponseIntegrity.UNCLOSED_BLOCK


def test_gecerli_yanit_saglam():
    assert (
        classify_response("iş tamam, dosyayı yazdım", truncated=False, has_tool_calls=False)
        is ResponseIntegrity.OK
    )


def test_arac_cagrisi_varsa_metin_bos_olsa_bile_saglam():
    """Araç çağıran tur metin üretmeyebilir; bu kayıp değildir."""
    sonuc = classify_response("", truncated=False, has_tool_calls=True)

    assert sonuc is ResponseIntegrity.OK
