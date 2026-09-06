"""Sağlayıcı yeteneği elle yazılmaz, GÖZLEMDEN çıkarılır.

Bugün görsel taşıma, bağlam uzunluğu ve araç çağrısı desteği elle yapılandırılıyor
ve yapılandırma yanlışsa Fusion modelin yapamayacağı bir şeyi deneyip turu yakıyor
(ölçüldü: görsel desteklemeyen web yolunda `Message.images` sessizce düşüyordu).

Sonuç UYDURULMAZ: sondaj yapılamadıysa yetenek `UNKNOWN` kalır — "bilmiyoruz" ayrı
bir durumdur ve "kesinlikle var" gibi davranılmaz.
"""

from __future__ import annotations

from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.engines.capability_probe import probe_from_samples


def test_gecerli_arac_blogu_native_olmayan_destegi_kanitlar():
    yetenek = probe_from_samples(
        tool_call_text='FUSION_TOOL_CALL{"name":"read_file","arguments":{"path":"a.py"}}FUSION_TOOL_CALL_END',
        image_echo="gördüm: kırmızı kare",
        image_marker="kırmızı kare",
    )

    assert yetenek.tool_support is ToolSupport.EMULATED
    assert yetenek.vision is True


def test_bozuk_blok_destegi_kanitlamaz():
    yetenek = probe_from_samples(tool_call_text="Tabii, dosyayı okuyorum.", image_echo="")

    assert yetenek.tool_support is ToolSupport.NONE
    assert yetenek.vision is False


def test_sondaj_yapilamadiysa_bilinmiyor_kalir():
    yetenek = probe_from_samples(tool_call_text=None, image_echo=None)

    assert yetenek.tool_support is ToolSupport.UNKNOWN
    assert yetenek.vision is False


def test_yanlis_gorsel_cevabi_vision_saymaz():
    """Model "gördüm" demiş olabilir; işaret eşleşmiyorsa kanıt yoktur."""
    yetenek = probe_from_samples(
        tool_call_text=None, image_echo="elbette görselleri işleyebilirim", image_marker="mor üçgen"
    )

    assert yetenek.vision is False
