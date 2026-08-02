"""Taklit araç çağrısı — SAF format ve ayrıştırma (üçüncü parti bağımlılığı yok).

Native tool-calling'i olmayan modeller için araç tanımları prompt'a TEK canonical
biçimde eklenir ve modelin çıktısı `ToolCall`'a ayrıştırılır (master prompt §5.3).
Bu modül `core` sözleşmesine uyar: yalnızca stdlib. JSON schema DOĞRULAMASI (jsonschema
gerektiren) ayrı bir katmandadır (`tools.emulation`); bu modül yalnızca biçim/ayrıştırma
tutar, böylece hem `providers` (web adapter) hem `tools` ondan yararlanabilir.

Tasarım kuralları:
- **Tek canonical format**: `<tool_call>{json}</tool_call>`. İkinci biçim yoktur.
- **Doğal metin yanlışlıkla tool call sayılmaz**: yalnızca sınır işaretleri arasındaki
  geçerli JSON bloklar çağrı olur; dışındaki metin nihai cevaptır.
- **Bozuk blok reddedilir**, sessizce yutulmaz: hata sınıflandırılıp döndürülür.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .types import ToolCall

#: Tek canonical sınır işaretleri. Model çağrıyı BUNLARIN arasına yazar.
CALL_OPEN = "<tool_call>"
CALL_CLOSE = "</tool_call>"

_BLOCK = re.compile(re.escape(CALL_OPEN) + r"(.*?)" + re.escape(CALL_CLOSE), re.DOTALL)


def render_tool_instructions(schemas: Sequence[Mapping[str, object]]) -> str:
    """Araç tanımlarını prompt'a eklenecek TALİMAT bloğuna çevir.

    Model bu bloğu okuyup gerektiğinde `<tool_call>{"name": …, "arguments": {…}}
    </tool_call>` biçiminde çağrı üretir. Araç kullanmayacaksa yalnızca düz cevabını
    yazar — blok dışı metin nihai cevaptır.
    """
    satirlar = [
        "Araç kullanman gerekirse ŞU biçimde çağır (başka biçim geçersizdir):",
        f"{CALL_OPEN}" + '{"name": "araç_adı", "arguments": {…}}' + f"{CALL_CLOSE}",
        "Birden çok çağrı için her birini ayrı bloğa yaz. Araç kullanmıyorsan blok yazma.",
        "",
        "Kullanılabilir araçlar:",
    ]
    for schema in schemas:
        function = schema.get("function")
        if not isinstance(function, Mapping):
            continue
        name = function.get("name", "")
        description = function.get("description", "")
        parameters = function.get("parameters", {})
        satirlar.append(f"- {name}: {description}")
        satirlar.append(f"  parametreler: {json.dumps(parameters, ensure_ascii=False)}")
    return "\n".join(satirlar)


@dataclass(frozen=True, slots=True)
class EmulatedParse:
    """Bir model çıktısının ayrıştırılmış hâli."""

    #: Geçerli çağrılar.
    calls: tuple[ToolCall, ...]
    #: Blok DIŞINDAKİ metin (nihai cevap ya da düşünme).
    text: str
    #: Bozuk blokların sınıflandırılmış hataları.
    errors: tuple[str, ...]


def parse_tool_calls(text: str) -> EmulatedParse:
    """Model çıktısından taklit araç çağrılarını çıkar.

    Yalnızca sınır işaretleri arasındaki GEÇERLİ JSON bloklar çağrı sayılır. Bozuk
    JSON ya da `name` eksikliği hata olarak döner (sahte çağrı üretilmez). Blok
    dışındaki metin nihai cevap olarak `text`'te toplanır.
    """
    calls: list[ToolCall] = []
    errors: list[str] = []
    for index, match in enumerate(_BLOCK.finditer(text)):
        ham = match.group(1).strip()
        try:
            obj = json.loads(ham)
        except json.JSONDecodeError as hata:
            errors.append(f"blok {index}: geçersiz JSON ({hata.msg})")
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("name"), str):
            errors.append(f"blok {index}: 'name' alanı eksik ya da metin değil")
            continue
        arguments = obj.get("arguments", {})
        if not isinstance(arguments, dict):
            errors.append(f"blok {index}: 'arguments' bir nesne olmalı")
            continue
        calls.append(
            ToolCall(
                id=f"emu-{index}",
                name=obj["name"],
                arguments=json.dumps(arguments, ensure_ascii=False),
            )
        )
    disi = _BLOCK.sub("", text).strip()
    return EmulatedParse(calls=tuple(calls), text=disi, errors=tuple(errors))
