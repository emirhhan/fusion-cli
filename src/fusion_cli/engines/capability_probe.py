"""Sağlayıcı yeteneğini GÖZLEMDEN çıkarır.

Görsel taşıma, araç çağrısı desteği ve bağlam uzunluğu bugün elle yapılandırılıyor.
Yapılandırma yanlışsa Fusion modelin yapamayacağı bir şeyi deniyor ve turu yakıyor
(ölçüldü: görsel desteklemeyen web yolunda `Message.images` sessizce düşüyordu).

Bu modül SAF karar verir: küçük sondaj yanıtlarını alır, kanıt varsa yeteneği
işaretler. Sondaj yapılamadıysa `UNKNOWN` kalır — "bilmiyoruz" ayrı bir durumdur ve
uygunluk kararında "kesinlikle var" gibi davranılmaz (`core.model_capability`).

Sondajın kendisini (ağ çağrısı) üst katman yapar; burada yalnız çıkarım vardır ve
bu yüzden test edilebilir.
"""

from __future__ import annotations

from ..core.model_capability import ModelCapability, ToolSupport
from ..core.tool_emulation import parse_tool_calls


def probe_from_samples(
    *,
    tool_call_text: str | None,
    image_echo: str | None,
    image_marker: str = "",
    context_window: int = 0,
) -> ModelCapability:
    """Sondaj yanıtlarından yeteneği çıkar.

    `tool_call_text`: modelden istenen örnek araç çağrısının ham yanıtı.
    `image_echo`: modele gösterilen görselde ne yazdığını soran sondajın yanıtı.
    `image_marker`: görselde gerçekten bulunan işaret; yanıt bunu içermeli.
    """
    return ModelCapability(
        tool_support=_tool_support(tool_call_text),
        vision=_vision(image_echo, image_marker),
        context_window=context_window,
    )


def _tool_support(text: str | None) -> ToolSupport:
    """Yanıt gerçekten AYRIŞTIRILABİLİR bir çağrı içeriyor mu?

    Modelin "araç kullanabilirim" demesi kanıt değildir; kanıt, sözleşmeye uygun
    bir blok üretmesidir.
    """
    if text is None:
        return ToolSupport.UNKNOWN
    parse = parse_tool_calls(text)
    return ToolSupport.EMULATED if parse.calls else ToolSupport.NONE


def _vision(echo: str | None, marker: str) -> bool:
    """Model görseldeki İŞARETİ okuyabildi mi?

    "Görselleri işleyebilirim" cümlesi kanıt değildir: işaret eşleşmiyorsa görsel
    hiç ulaşmamış olabilir ve bu fark, turun sessizce boşa gitmesi demektir.
    """
    if not echo or not marker:
        return False
    return marker.casefold() in echo.casefold()
