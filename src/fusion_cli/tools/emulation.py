"""Taklit araç çağrısı — JSON schema DOĞRULAMASI.

Biçim ve ayrıştırma `core.tool_emulation`'dadır (saf, üçüncü parti yok). Bu modül yalnızca
`jsonschema` gerektiren argüman doğrulamasını ekler ve saf parçaları YENİDEN DIŞA AKTARIR
(geriye uyum): çağıranlar tek yerden `tools.emulation`'ı kullanabilir.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..core.tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    EmulatedParse,
    parse_tool_calls,
    render_tool_instructions,
)

__all__ = [
    "CALL_CLOSE",
    "CALL_OPEN",
    "EmulatedParse",
    "parse_tool_calls",
    "render_tool_instructions",
    "validate_arguments",
]


def validate_arguments(
    function_schema: Mapping[str, object], arguments: Mapping[str, object]
) -> tuple[str, ...]:
    """Çağrı argümanlarını aracın JSON şemasına karşı doğrula; hataları döndür.

    Şema yoksa doğrulama atlanır (hata döndürülmez). Doğrulama başarılıysa boş demet.
    Ağır import: `jsonschema` yalnızca gerçekten doğrulama gerektiğinde yüklenir.
    """
    parameters = function_schema.get("parameters")
    if not isinstance(parameters, Mapping):
        return ()
    import jsonschema

    validator = jsonschema.Draft202012Validator(dict(parameters))
    return tuple(error.message for error in validator.iter_errors(dict(arguments)))
