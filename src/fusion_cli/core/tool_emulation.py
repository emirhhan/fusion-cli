"""Taklit araç çağrısı ve ham payload biçimlendirme/ayrıştırma — kanonik sözleşme.

Native function-calling'i olmayan modeller (web arayüzleri) araç çağrısını METİN
olarak üretir. Bu modül o metnin tek geçerli biçimini tanımlar ve geri okur.

İki blok vardır ve ayrı olmaları zorunludur:

- `<tool_call>{…}</tool_call>` — çağrının kendisi, tek satırlık JSON.
- `<tool_payload id="…">…</tool_payload>` — çok satırlı/kod içeren değerler.
  JSON string'inin içine kaynak kodu koymak kaçış karakterlerinde bozuluyordu;
  payload ayrı taşınır ve çağrıdan `{"$ref": "id"}` ile gösterilir.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .types import ToolCall

CALL_OPEN = "<tool_call>"
CALL_CLOSE = "</tool_call>"
PAYLOAD_OPEN = "<tool_payload"
PAYLOAD_CLOSE = "</tool_payload>"
PAYLOAD_SENTINEL = "FUSION_RAW_PAYLOAD_V1"

_BLOCK = re.compile(
    re.escape(CALL_OPEN) + r"(.*?)" + re.escape(CALL_CLOSE),
    re.DOTALL,
)
_PAYLOAD_ID = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}"
_PAYLOAD_BLOCK = re.compile(
    rf'<tool_payload\s+id="(?P<id>{_PAYLOAD_ID})"(?P<attrs>[^>]*)>'
    r"(?P<body>.*?)"
    + re.escape(PAYLOAD_CLOSE),
    re.DOTALL,
)
_PAYLOAD_LINES_ATTR = re.compile(r'\blines\s*=\s*"(?P<lines>\d{1,6})"')


class _PayloadResolutionError(ValueError):
    """Bir payload referansı güvenli biçimde çözülemedi."""


#: Payload gövdesinin kaç satır olduğunu söyleyen ZORUNLU bütünlük sinyali.
#
# Neden satır sayısı: web arayüzü payload'a dokunabiliyor (dil rozeti ekliyor, kod
# bloğu sınırı koyuyor, satır kırıyor). Bozulmayı ÖNLEYEMEYİZ ama FARK EDEBİLİRİZ —
# ve fark edilmeyen bozulma kullanıcının dosyasına bozuk içerik yazmak demektir.
#
# Neden checksum ya da base64 değil: ikisi de modelin kendi ürettiği metni
# kodlamasını/özetlemesini ister. Modeller bunu güvenilir yapmaz, uydurur; sonuç
# "doğrulandı" sanılan ama aslında hiç doğrulanmamış bir taşıma olurdu. Satır
# sayısını model zaten bilir: satırları o yazıyor.
def _expected_lines(attributes: str) -> int | None:
    match = _PAYLOAD_LINES_ATTR.search(attributes)
    return int(match.group("lines")) if match else None


def _verify_line_count(body: str, expected: int | None, payload_id: str) -> None:
    """Geri okunan gövde, modelin bildirdiği satır sayısıyla uyuşuyor mu?"""
    if expected is None:
        raise _PayloadResolutionError(
            f'payload {payload_id}: lines="N" özniteliği zorunlu — '
            "gövdenin kaç satır olduğunu bildir ki taşıma sırasında bozulma fark edilsin"
        )
    actual = len(body.splitlines())
    if actual != expected:
        raise _PayloadResolutionError(
            f"payload {payload_id}: bildirilen {expected} satır, geri okunan {actual} satır. "
            "Gövde taşıma sırasında bozulmuş olabilir; içerik YAZILMADI. "
            "Payload'ı olduğu gibi yeniden gönder ve lines değerini doğru say."
        )


def _example_value(name: str, schema: Mapping[str, object]) -> object:
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes)) and enum:
        return enum[0]
    kind = schema.get("type")
    if kind == "boolean":
        return False
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "array":
        return []
    if kind == "object":
        return {}
    examples = {
        "path": "path/to/file",
        "content": "file content",
        "command": "python3 -m pytest -q",
        "pattern": "**/*.py",
        "query": "search query",
        "url": "https://example.com",
        "subcommand": "status",
    }
    return examples.get(name.lower(), "value")


def render_tool_example(function_schema: Mapping[str, object]) -> str:
    """Şemadan geçerli TEK bir kanonik kısa-çağrı örneği üret."""
    name = str(function_schema.get("name", "tool"))
    parameters = function_schema.get("parameters")
    arguments: dict[str, object] = {}
    if isinstance(parameters, Mapping):
        properties = parameters.get("properties")
        required = parameters.get("required")
        if (
            isinstance(properties, Mapping)
            and isinstance(required, Sequence)
            and not isinstance(required, (str, bytes))
        ):
            for field in required:
                if not isinstance(field, str):
                    continue
                raw_schema = properties.get(field, {})
                schema = raw_schema if isinstance(raw_schema, Mapping) else {}
                arguments[field] = _example_value(field, schema)
    payload = {"name": name, "arguments": arguments}
    return f"{CALL_OPEN}{json.dumps(payload, ensure_ascii=False)}{CALL_CLOSE}"


#: Payload protokolünün TEK örneği ve TEK kural listesi.
#
# Bu metin eskiden iki yerde (talimat üretimi ve onarım notu) ayrı ayrı yazılıydı ve
# geçmişte her düzeltmede ikisi birlikte elle güncellendi — biri unutulsa model iki
# farklı sözleşme görürdü. Artık tek kaynak: iki çağıran da bunu kullanır.
PAYLOAD_EXAMPLE = "\n".join(
    [
        '<tool_payload id="file-1" lines="2">',
        "```python",
        PAYLOAD_SENTINEL,
        "def greet(name: str) -> str:",
        '    return f"Hello, {name}!"',
        "```",
        "</tool_payload>",
        CALL_OPEN
        + json.dumps(
            {
                "name": "write_file",
                "arguments": {"path": "greet.py", "content": {"$ref": "file-1"}},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + CALL_CLOSE,
    ]
)

PAYLOAD_RULES = (
    "- Kaynak kodu JSON content stringinin içine koyma; payload kullan.",
    "- Çok satırlı, tırnak ya da ters eğik çizgi içeren her içerik payload'a girer.",
    "- Payload gövdesini Markdown kod bloğu (```dil ... ```) içine koy.",
    f"- Kod bloğunun ilk içerik satırı tam olarak {PAYLOAD_SENTINEL} olmalı; "
    "web arayüzünün eklediği dil rozeti bu satırdan önce güvenle ayıklanır.",
    '- lines="N" ZORUNLUDUR: gövdenin (sentinel hariç) satır sayısını doğru yaz. '
    "Uyuşmazsa içerik yazılmaz; bu, taşıma sırasında bozulmayı yakalayan tek kontroldür.",
    "- Her payload id benzersiz olmalı ve tam olarak bir $ref ile kullanılmalı.",
    '- Payload referansı yalnızca {"$ref":"payload-id"} biçimindedir, başka alan almaz.',
)

_GENERAL_RULES = (
    "- name alanı zorunludur ve boş olamaz.",
    "- arguments alanı zorunludur ve her zaman JSON nesnesidir.",
    "- Şemadaki required alanlarının tamamını doğru tipte gönder.",
    "- Aynı çağrıyı aynı argümanlarla tekrar etme.",
    "- Araç kullanmayacaksan tool_call bloğu yazma; nihai cevabı ver.",
)


def render_tool_instructions(schemas: Sequence[Mapping[str, object]]) -> str:
    """Kanonik kısa-çağrı ve ham-payload araç sözleşmesini metne dök."""
    lines = [
        "Araç kullanacaksan YALNIZCA aşağıdaki iki blok biçimini kullan.",
        "",
        "1) Tek satırlık değerler için kısa çağrı:",
        f'{CALL_OPEN}{{"name":"read_file","arguments":{{"path":"src/app.py"}}}}{CALL_CLOSE}',
        "",
        "2) Çok satırlı / kod içeren değerler için payload:",
        PAYLOAD_EXAMPLE,
        "",
        "Payload kuralları:",
        *PAYLOAD_RULES,
        "",
        "Genel kurallar:",
        *_GENERAL_RULES,
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
        lines.append(f"- {name}: {description}")
        lines.append(f"  parametreler: {json.dumps(parameters, ensure_ascii=False)}")
        lines.append(f"  kısa değer örneği: {render_tool_example(function)}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class EmulatedParse:
    calls: tuple[ToolCall, ...]
    text: str
    errors: tuple[str, ...]


def _strip_payload_transport_prefix(body: str) -> str:
    """Sentinel'i ve ondan ÖNCE gelen tarayıcı araç çubuğu satırlarını at.

    Web arayüzü kod bloğunun başına dil rozeti ("python", "Kopyala") ekleyebiliyor;
    sentinel bu gürültünün nerede bittiğini kesin olarak işaretler.
    """
    lines = body.splitlines(keepends=True)
    for index, line in enumerate(lines[:4]):
        if line.rstrip("\r\n") == PAYLOAD_SENTINEL:
            return "".join(lines[index + 1 :])

    # Sentinel protokolünden ÖNCE gözlenen tek somut bozulma için geriye uyum:
    # Gemini kod bloğunun başına "python" rozeti koyuyor ve hemen ardından açıkça
    # kaynak kodu geliyordu. Yalnızca bu dar kalıp kurtarılır; genel bir tahmin
    # yapılmaz, çünkü yanlış tahmin kullanıcının dosyasına yanlış içerik yazar.
    first, separator, remainder = body.partition("\n")
    python_starts = (
        "import ",
        "from ",
        "def ",
        "class ",
        "@",
        "if __name__",
        "#!",
    )
    if (
        separator
        and first.strip().casefold() == "python"
        and remainder.lstrip().startswith(python_starts)
    ):
        return remainder
    return body


def _normalize_payload_body(body: str) -> str:
    """Payload çerçevesini, kod bloğu sınırlarını ve tarayıcı etiketlerini temizle."""
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    if body.endswith("\r\n"):
        body = body[:-2]
    elif body.endswith("\n"):
        body = body[:-1]

    if body.startswith("```"):
        fenced = re.fullmatch(
            r"```[^\r\n]*\r?\n(?P<body>.*)\r?\n```[ \t]*",
            body,
            flags=re.DOTALL,
        )
        if fenced is None:
            raise _PayloadResolutionError(
                "payload code fence kapanmadı veya geçersiz"
            )
        body = fenced.group("body")

    return _strip_payload_transport_prefix(body)


def _resolve_payload_refs(
    value: object,
    payloads: Mapping[str, str],
    used: set[str],
    *,
    path: str,
) -> object:
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"}:
                raise _PayloadResolutionError(
                    f"{path}: $ref nesnesi başka alan içeremez"
                )
            ref = value["$ref"]
            if not isinstance(ref, str) or not ref:
                raise _PayloadResolutionError(
                    f"{path}.$ref: boş olmayan metin olmalı"
                )
            if ref not in payloads:
                raise _PayloadResolutionError(
                    f"{path}.$ref: payload bulunamadı: {ref}"
                )
            used.add(ref)
            return payloads[ref]
        return {
            key: _resolve_payload_refs(
                item,
                payloads,
                used,
                path=f"{path}.{key}",
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_payload_refs(
                item,
                payloads,
                used,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    return value


def parse_tool_calls(text: str) -> EmulatedParse:
    """Kanonik çağrıları çıkar ve ham payload referanslarını çöz."""
    calls: list[ToolCall] = []
    errors: list[str] = []
    payloads: dict[str, str] = {}
    used_payloads: set[str] = set()

    for match in _PAYLOAD_BLOCK.finditer(text):
        payload_id = match.group("id")
        if payload_id in payloads:
            errors.append(f"yinelenen payload id: {payload_id}")
            continue
        try:
            body = _normalize_payload_body(match.group("body"))
            # Bütünlük kontrolü çerçeve TEMİZLENDİKTEN sonra yapılır: sayılması
            # gereken şey modelin yazdığı içerik, taşımanın eklediği gürültü değil.
            _verify_line_count(body, _expected_lines(match.group("attrs")), payload_id)
        except _PayloadResolutionError as error:
            # Bütünlük hataları payload kimliğini zaten taşır; çerçeve hataları taşımaz.
            detail = str(error)
            if not detail.startswith("payload "):
                detail = f"payload {payload_id}: {detail}"
            errors.append(detail)
            continue
        payloads[payload_id] = body

    without_payloads = _PAYLOAD_BLOCK.sub("", text)
    if PAYLOAD_OPEN in without_payloads or PAYLOAD_CLOSE in without_payloads:
        errors.append("kapanmamış veya geçersiz tool_payload bloğu")

    for index, match in enumerate(_BLOCK.finditer(without_payloads)):
        raw = match.group(1).strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as error:
            errors.append(f"blok {index}: geçersiz JSON ({error.msg})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"blok {index}: çağrı bir JSON nesnesi olmalı")
            continue
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"blok {index}: 'name' alanı zorunlu ve boş olamaz")
            continue
        if "arguments" not in obj:
            errors.append(f"blok {index}: 'arguments' alanı zorunlu")
            continue
        arguments = obj["arguments"]
        if not isinstance(arguments, dict):
            errors.append(f"blok {index}: 'arguments' bir JSON nesnesi olmalı")
            continue
        try:
            resolved = _resolve_payload_refs(
                arguments,
                payloads,
                used_payloads,
                path=f"blok {index}.arguments",
            )
        except _PayloadResolutionError as error:
            errors.append(str(error))
            continue
        calls.append(
            ToolCall(
                id=f"emu-{index}",
                name=name.strip(),
                arguments=json.dumps(resolved, ensure_ascii=False),
            )
        )

    for payload_id in sorted(set(payloads) - used_payloads):
        errors.append(f"payload kullanılmadı: {payload_id}")

    outside = _BLOCK.sub("", without_payloads)
    if CALL_OPEN in outside or CALL_CLOSE in outside:
        errors.append("kapanmamış veya eşleşmeyen tool_call sınır işareti")

    return EmulatedParse(
        calls=tuple(calls),
        text=outside.strip(),
        errors=tuple(errors),
    )
