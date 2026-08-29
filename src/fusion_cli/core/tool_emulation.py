"""Taklit araç çağrısı ve ham payload biçimlendirme/ayrıştırma — kanonik sözleşme.

Native function-calling'i olmayan modeller (web arayüzleri) araç çağrısını METİN
olarak üretir. Bu modül o metnin tek geçerli biçimini tanımlar ve geri okur.

İki blok vardır ve ayrı olmaları zorunludur:

- **Çağrı** — tek satırlık JSON, `FUSION_TOOL_CALL` / `FUSION_TOOL_CALL_END` arasında.
- **Payload** — çok satırlı/kod içeren değerler. JSON string'inin içine kaynak kodu
  koymak kaçış karakterlerinde bozuluyordu; payload ayrı taşınır ve çağrıdan
  `{"$ref": "id"}` ile gösterilir.

SINIRLAYICI NEDEN DÜZ METİN — ölçüldü (Gemini web, 5 senaryo):

Sınırlayıcılar eskiden `<tool_call>…</tool_call>` biçimindeydi. Araç isteyen dört
senaryonun DÖRDÜ de tamamen BOŞ yanıt döndürdü; araç istemeyen beşinci senaryo
kusursuz cevapladı. Aradaki tek fark, modelin bu bloğu üretmeye çalışmasıydı.

Sebep: HTML'e benzeyen bir sınırlayıcı, HTML render eden bir kanalda kullanılıyordu.
Sıkı bir temizleyici bilinmeyen elemanı ÇOCUKLARIYLA BİRLİKTE atar — mesaj boşalır.
Model bloğu üretti, arayüz sildi, Fusion "model boş cevap verdi" sandı ve tur hiçbir
iş yapmadan bitti.

Yeni sınırlayıcılar kendi satırlarında duran düz büyük harfli işaretlerdir: ne HTML
ne Markdown anlamı taşırlar, bu yüzden render edilirken hiçbir dönüşüme uğramazlar.
Aynı desen `PAYLOAD_SENTINEL` ile zaten çalışıyordu.

Eski biçim OKUMADA korunur: sözleşme değişse de yarıda kalmış bir konuşmadaki blok
ayrıştırılabilmelidir. Üretilen talimat yalnızca yeni biçimi öğretir.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .types import ToolCall

#: Kanonik sınırlayıcılar. Kendi satırlarında dururlar ve düz metindir.
CALL_OPEN = "FUSION_TOOL_CALL"
CALL_CLOSE = "FUSION_TOOL_CALL_END"
PAYLOAD_OPEN = "FUSION_PAYLOAD"
PAYLOAD_CLOSE = "FUSION_PAYLOAD_END"
PAYLOAD_SENTINEL = "FUSION_RAW_PAYLOAD_V1"

#: Eski HTML-benzeri sınırlayıcılar — YALNIZCA okumada desteklenir.
LEGACY_CALL_OPEN = "<tool_call>"
LEGACY_CALL_CLOSE = "</tool_call>"
LEGACY_PAYLOAD_CLOSE = "</tool_payload>"

# Sınırlayıcılar satır başına SABİTLENMEZ: model çoğu zaman "Şunu yapıyorum."
# dedikten sonra bloğu aynı satırda açıyor ve katı bir çapa bunu kaçırırdı.
# İşaretler benzersiz büyük harfli dizeler olduğu için çapaya gerek de yok.
_BLOCK = re.compile(
    rf"{re.escape(CALL_OPEN)}\s*(?P<body>.*?)\s*{re.escape(CALL_CLOSE)}",
    re.DOTALL,
)
_LEGACY_BLOCK = re.compile(
    re.escape(LEGACY_CALL_OPEN) + r"(?P<body>.*?)" + re.escape(LEGACY_CALL_CLOSE),
    re.DOTALL,
)
_PAYLOAD_ID = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}"
_PAYLOAD_BLOCK = re.compile(
    rf'{re.escape(PAYLOAD_OPEN)}\s+id="(?P<id>{_PAYLOAD_ID})"(?P<attrs>[^\r\n]*)'
    r"\r?\n(?P<body>.*?)"
    rf"{re.escape(PAYLOAD_CLOSE)}",
    re.DOTALL,
)
_LEGACY_PAYLOAD_BLOCK = re.compile(
    rf'<tool_payload\s+id="(?P<id>{_PAYLOAD_ID})"(?P<attrs>[^>]*)>'
    r"(?P<body>.*?)" + re.escape(LEGACY_PAYLOAD_CLOSE),
    re.DOTALL,
)
_PAYLOAD_LINES_ATTR = re.compile(r'\blines\s*=\s*"(?P<lines>\d{1,6})"')


class _PayloadResolutionError(ValueError):
    """Bir payload referansı güvenli biçimde çözülemedi."""


#: Payload bütünlüğü MODELİN ARİTMETİĞİNE değil, BİZİM doğrulayabildiğimiz yapıya
#: dayanır.
#
# Önce `lines="N"` zorunluydu: model gövdenin satır sayısını bildirecek, biz geri
# okuduğumuzla karşılaştıracaktık. Canlı ölçüm bunu çürüttü — dört payload denemesinde
# sıfır gerçek bozulma yakalandı, buna karşılık İKİ kez doğru taşınmış içerik reddedildi
# ve ikisinde de görev tamamen durdu:
#
#   bildirilen 3  / geri okunan 2   → sondaki boş satır sayılmış
#   bildirilen 33 / geri okunan 28  → dil rozeti, sentinel ve kod bloğu çiti sayılmış
#
# Model gövdeyi doğru üretiyor ama ÇERÇEVEYİ de sayıyor; sayım hatası çerçevenin
# biçimine göre değişiyor ve talimatla düzeltilemiyor. Bu yüzden sayım artık kabul
# ölçütü değildir.
#
# Yerine geçen kontroller, modelden hiçbir şey istemeden bozulmayı yakalar:
#   - kapanış işareti yoksa blok kırpılmıştır (ayrı hata)
#   - sentinel varsa içeriğin nerede başladığı KESİNDİR (rozet/çit güvenle atılır)
#   - içerikte çerçeve işareti kalmışsa temizleme başarısızdır
#   - gövde boşsa taşınacak bir şey gelmemiştir
#
# `lines` hâlâ ayrıştırılır ve bir uyuşmazlık taşıma sorunu SEZDİRİR; ama tek başına
# içeriği reddetmez. Yanlış alarmın bedeli, yakalamadığı riskten büyüktü.
def _expected_lines(attributes: str) -> int | None:
    match = _PAYLOAD_LINES_ATTR.search(attributes)
    return int(match.group("lines")) if match else None


#: Temizlenmiş gövdede ASLA kalmaması gereken çerçeve işaretleri.
_FRAMING_LEAKS = (PAYLOAD_SENTINEL, PAYLOAD_OPEN, PAYLOAD_CLOSE, CALL_OPEN, CALL_CLOSE)


def _verify_payload_body(body: str, payload_id: str) -> None:
    """Gövde yapısal olarak sağlam mı? Model aritmetiği kullanılmaz."""
    if not body.strip():
        raise _PayloadResolutionError(f"payload {payload_id}: gövde boş — içerik taşınmamış")
    for leak in _FRAMING_LEAKS:
        if leak in body:
            raise _PayloadResolutionError(
                f"payload {payload_id}: çerçeve işareti içerikte kaldı ({leak}). "
                "Payload gövdesini kod bloğu içinde ve sentinel'den SONRA yaz."
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
    return render_call(payload)


def render_call(payload: Mapping[str, object]) -> str:
    """Bir çağrıyı kanonik bloğa sar. Sınırlayıcılar KENDİ satırlarında durur."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"{CALL_OPEN}\n{body}\n{CALL_CLOSE}"


#: Payload protokolünün TEK örneği ve TEK kural listesi.
#
# Bu metin eskiden iki yerde (talimat üretimi ve onarım notu) ayrı ayrı yazılıydı ve
# geçmişte her düzeltmede ikisi birlikte elle güncellendi — biri unutulsa model iki
# farklı sözleşme görürdü. Artık tek kaynak: iki çağıran da bunu kullanır.
PAYLOAD_EXAMPLE = "\n".join(
    [
        f'{PAYLOAD_OPEN} id="file-1"',
        "```python",
        PAYLOAD_SENTINEL,
        "def greet(name: str) -> str:",
        '    return f"Hello, {name}!"',
        "```",
        PAYLOAD_CLOSE,
        render_call(
            {
                "name": "write_file",
                "arguments": {"path": "greet.py", "content": {"$ref": "file-1"}},
            }
        ),
    ]
)

#: Kısmi düzenlemenin V2 örneği: eski kodu model tekrar üretmez.
# `read_file` çıktısındaki 1-tabanlı satır numaraları kullanılır; güvenlik, araç
# katmanının sakladığı dosya revision'ıyla sağlanır. Böylece iki büyük payload yerine
# yalnızca YENİ içerik taşınır ve çağrı bloğuna varmadan kesilme riski düşer.
RANGE_EDIT_EXAMPLE = "\n".join(
    [
        f'{PAYLOAD_OPEN} id="yeni-aralik-1"',
        "```python",
        PAYLOAD_SENTINEL,
        "def topla(a, b):",
        "    return a + b",
        "```",
        PAYLOAD_CLOSE,
        render_call(
            {
                "name": "replace_range",
                "arguments": {
                    "path": "hesap.py",
                    "start_line": 10,
                    "end_line": 11,
                    "new": {"$ref": "yeni-aralik-1"},
                },
            }
        ),
    ]
)


#: Var olan bir dosyayı kısmen değiştirmenin işlenmiş örneği.
#
# Bu örneğin varlık sebebi ölçülmüş bir davranıştır: sözleşmedeki TEK mutasyon
# örneği `write_file` idi ve taklit araç kullanan model çok satırlı bir düzenleme
# gerektiğinde dosyanın TAMAMINI yeniden yazıyordu. Mekanizma zaten çalışıyordu —
# tek çağrıda iki payload sorunsuz ayrışıyor — ama modele bunun mümkün olduğu
# hiç gösterilmemişti. Model elindeki tek örneği taklit ediyordu; kusur bizdeydi.
#
# Tam dosya yazmanın bedeli: dokunulmaması gereken satırlar yeniden üretilir,
# yorum/boş satır düzeni kayar ve model dosyanın okumadığı kısmını uydurabilir.
EDIT_EXAMPLE = "\n".join(
    [
        f'{PAYLOAD_OPEN} id="eski-1"',
        "```python",
        PAYLOAD_SENTINEL,
        "def topla(a, b):",
        "    return a - b",
        "```",
        PAYLOAD_CLOSE,
        f'{PAYLOAD_OPEN} id="yeni-1"',
        "```python",
        PAYLOAD_SENTINEL,
        "def topla(a, b):",
        "    return a + b",
        "```",
        PAYLOAD_CLOSE,
        render_call(
            {
                "name": "edit_file",
                "arguments": {
                    "path": "hesap.py",
                    "old": {"$ref": "eski-1"},
                    "new": {"$ref": "yeni-1"},
                },
            }
        ),
    ]
)

PAYLOAD_RULES = (
    "- Kod veya çok satırlı içerikleri JSON stringine gömme; payload kullan.",
    f"- Payload gövdesi Markdown kod bloğunda olmalı ve ilk içerik satırı "
    f"{PAYLOAD_SENTINEL} olmalı.",
    f"- Her payload {PAYLOAD_CLOSE} ile kapanır; benzersiz id yalnız "
    '{"$ref":"id"} biçiminde kullanılır.',
)

_GENERAL_RULES = (
    "- name ve arguments zorunludur; arguments JSON nesnesidir ve şemaya uymalıdır.",
    "- Mevcut dosyanın BİR BÖLÜMÜNÜ değiştireceksen önce read_file ile gör, sonra "
    "replace_range kullan; write_file DEĞİL.",
    "- replace_range ile yalnız YENİ içeriği gönder; Eski içeriği tekrar üretme.",
    "- write_file yeni/tam dosya yazımı içindir; edit_file yalnız kısa exact-text "
    "fallback aracıdır.",
    "- Bir yanıtta EN FAZLA BİR DEĞİŞTİRİCİ çağrı yap "
    "(write_file, replace_range, edit_file, multi_edit, run_shell).",
    "- Bağımsız OKUMA çağrılarını aynı yanıtta BİRDEN ÇOK yapabilirsin.",
    "- Aynı çağrıyı aynı argümanlarla tekrar etme.",
    "- Araç gerekmiyorsa tool-call bloğu üretme; nihai cevabı ver.",
)


def _instruction_schema(value: object) -> object:
    """Emulated prompt için schema description tekrarlarını kaldır."""
    if isinstance(value, Mapping):
        return {
            key: _instruction_schema(item) for key, item in value.items() if key != "description"
        }
    if isinstance(value, list):
        return [_instruction_schema(item) for item in value]
    if isinstance(value, tuple):
        return [_instruction_schema(item) for item in value]
    return value


def render_tool_instructions(schemas: Sequence[Mapping[str, object]]) -> str:
    """Kanonik kısa-çağrı ve ham-payload araç sözleşmesini metne dök."""
    lines = [
        "Araç kullanacaksan yalnız aşağıdaki çağrı biçimlerini kullan.",
        "",
        "Kısa değer çağrısı:",
        f'{CALL_OPEN}{{"name":"read_file","arguments":{{"path":"src/app.py"}}}}{CALL_CLOSE}',
        "",
        "Kod / çok satırlı içerik payload örneği:",
        PAYLOAD_EXAMPLE,
        "",
        "Mevcut dosyada kısmi düzenleme örneği:",
        RANGE_EDIT_EXAMPLE,
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
        parameters = _instruction_schema(function.get("parameters", {}))

        lines.append(f"- {name}: {description}")
        lines.append(
            "  args: "
            + json.dumps(
                parameters,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

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

    # Sentinel yoksa geriye uyum: web arayüzü kod bloğunun başına DİL ROZETİ
    # koyuyor ve rozet payload'ın ilk satırı olarak geliyor.
    #
    # Ölçüldü (Gemini web): model doğru bir dosya üretti ama içeriğin ilk satırı
    # "JavaScript" oldu; dosya `ReferenceError: JavaScript is not defined` ile
    # bozuldu ve tur çöktü. Eskiden yalnızca küçük harfli "python" rozeti ve
    # yalnızca Python'a benzeyen bir gövde kurtarılıyordu.
    #
    # Tahmin YAPILMAZ: yalnızca BİLİNEN dil adları düşürülür. Uydurma bir
    # sezgisel kullanıcının dosyasına yanlış içerik yazardı.
    return body


def strip_fence_label(content: str, path: str) -> str:
    """Payload'ın ilk satırı, DOSYANIN DİLİNE ait bir kod bloğu rozetiyse düşür.

    Ölçüldü (Gemini web): model doğru bir `cart.js` üretti ama içeriğin ilk satırı
    "JavaScript" oldu; dosya `ReferenceError: JavaScript is not defined` ile
    bozuldu ve tur çöktü.

    Ayırt edici sinyal UZANTIDIR, kelimenin kendisi değil: `notes.txt` içeriği
    gerçekten "Python" kelimesiyle başlayabilir ve o içerik korunmalıdır. Rozet
    ancak hedef dosyanın diliyle eşleşiyorsa transport gürültüsüdür.
    """
    first, separator, remainder = content.partition("\n")
    if not separator or not remainder.strip():
        return content
    uzanti = path.rsplit(".", 1)[-1].casefold() if "." in path else ""
    return remainder if first.strip().casefold() in _LABELS_BY_EXT.get(uzanti, ()) else content


#: Dosya uzantısı → o dosyada rozet SAYILAN ilk satırlar.
#
# Eşleşme uzantıya bağlıdır: `notes.txt` içeriği "Python" ile başlayabilir ve
# korunur; `cart.js` içeriğinin "JavaScript" ile başlaması ise transport
# gürültüsüdür ve dosyayı bozar.
_LABELS_BY_EXT: Mapping[str, frozenset[str]] = {
    "js": frozenset({"javascript", "js"}),
    "mjs": frozenset({"javascript", "js"}),
    "cjs": frozenset({"javascript", "js"}),
    "jsx": frozenset({"javascript", "jsx"}),
    "ts": frozenset({"typescript", "ts"}),
    "tsx": frozenset({"typescript", "tsx"}),
    "py": frozenset({"python", "py"}),
    "rb": frozenset({"ruby"}),
    "go": frozenset({"go"}),
    "rs": frozenset({"rust"}),
    "java": frozenset({"java"}),
    "kt": frozenset({"kotlin"}),
    "swift": frozenset({"swift"}),
    "php": frozenset({"php"}),
    "sh": frozenset({"bash", "sh", "shell", "zsh"}),
    "sql": frozenset({"sql"}),
    "json": frozenset({"json", "jsonc"}),
    "yaml": frozenset({"yaml", "yml"}),
    "yml": frozenset({"yaml", "yml"}),
    "toml": frozenset({"toml"}),
    "html": frozenset({"html"}),
    "css": frozenset({"css"}),
    "scss": frozenset({"scss", "css"}),
    "xml": frozenset({"xml"}),
}


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
            raise _PayloadResolutionError("payload code fence kapanmadı veya geçersiz")
        body = fenced.group("body")

    return _strip_payload_transport_prefix(body)


def _apply_fence_strip(arguments: object) -> object:
    """Çözümlenmiş argümanlarda dil rozetini hedef dosyaya göre ayıkla.

    Yol ancak BURADA bilinir: payload çözümlenirken hangi alanı dolduracağı belli
    değildir, argümanlar tamamlandığında `path` elde olur.
    """
    if not isinstance(arguments, dict):
        return arguments
    hedef = arguments.get("path")
    if not isinstance(hedef, str):
        return arguments
    return {
        key: strip_fence_label(value, hedef) if isinstance(value, str) and key != "path" else value
        for key, value in arguments.items()
    }


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
                raise _PayloadResolutionError(f"{path}: $ref nesnesi başka alan içeremez")
            ref = value["$ref"]
            if not isinstance(ref, str) or not ref:
                raise _PayloadResolutionError(f"{path}.$ref: boş olmayan metin olmalı")
            if ref not in payloads:
                raise _PayloadResolutionError(f"{path}.$ref: payload bulunamadı: {ref}")
            used.add(ref)
            return payloads[ref]  # rozet ayıklaması `_apply_fence_strip`'te
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


def _payload_matches(text: str) -> list[re.Match[str]]:
    """Kanonik ve eski biçimdeki payload bloklarını metindeki SIRAYLA döndür."""
    matches = [*_PAYLOAD_BLOCK.finditer(text), *_LEGACY_PAYLOAD_BLOCK.finditer(text)]
    return sorted(matches, key=lambda match: match.start())


def _call_matches(text: str) -> list[re.Match[str]]:
    """Kanonik ve eski biçimdeki çağrı bloklarını metindeki SIRAYLA döndür."""
    matches = [*_BLOCK.finditer(text), *_LEGACY_BLOCK.finditer(text)]
    return sorted(matches, key=lambda match: match.start())


#: `name` alanının diğer sağlayıcı şemalarındaki karşılıkları.
#
# Model başka bir arayüzün biçimini hatırlayıp `{"tool": …}` yazdığında niyeti
# BELLİDİR; bunu hata sayıp bir onarım turu yakmak (tarayıcıda ~40 saniye) israftır.
_NAME_ALIASES = ("tool", "function", "tool_name")

#: `arguments` alanının karşılıkları.
_ARGS_ALIASES = ("parameters", "args", "input")

#: JSON'da nesne/dizi kapanışından hemen önce gelen fazla virgül.
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _loads_tolerant(raw: str) -> object | None:
    """JSON'u çöz; olmazsa ANLAMI DEĞİŞTİRMEYEN onarımları sırayla dene.

    Zayıf modellerin en sık dört sapmasından üçü burada sıfır maliyetle kapanır:
    sınırlayıcı çevresine markdown kalınlaştırması, sondaki fazla virgül ve
    gövdeyi saran kod çiti. Dördüncüsü (alan adlandırması) `_normalize_call_keys`
    içinde.

    Onarımlar yalnızca SÖZDİZİMİNE dokunur. Anlamı belirsiz bir gövdede hiçbir şey
    uydurulmaz; None döner ve çağıran taraf hatayı olduğu gibi bildirir.
    """
    for aday in (
        raw,
        raw.strip("*` \n"),
        _TRAILING_COMMA.sub(r"\1", raw),
        _TRAILING_COMMA.sub(r"\1", raw.strip("*` \n")),
    ):
        try:
            cozulmus: object = json.loads(aday)
        except json.JSONDecodeError:
            continue
        return cozulmus
    return None


def _normalize_call_keys(obj: dict[str, object]) -> dict[str, object]:
    """Alan adlandırma sapmalarını kanonik biçime çevir.

    İki sapma karşılanır: (1) `tool`/`parameters` gibi başka şemaların adları,
    (2) `arguments` alanının nesne yerine JSON STRING olarak gömülmesi — model
    kaçış karakterleriyle uğraşırken sık düşülen hata.

    Kanonik alan zaten VARSA takma ada bakılmaz: model ikisini birden yazmışsa
    açık olan kazanır, tahmin yürütülmez.
    """
    duzeltilmis = dict(obj)
    if "name" not in duzeltilmis:
        for takma in _NAME_ALIASES:
            if isinstance(duzeltilmis.get(takma), str):
                duzeltilmis["name"] = duzeltilmis.pop(takma)
                break
    if "arguments" not in duzeltilmis:
        for takma in _ARGS_ALIASES:
            if takma in duzeltilmis:
                duzeltilmis["arguments"] = duzeltilmis.pop(takma)
                break
    ham = duzeltilmis.get("arguments")
    if isinstance(ham, str):
        cozulmus = _loads_tolerant(ham)
        if isinstance(cozulmus, dict):
            duzeltilmis["arguments"] = cozulmus
    return duzeltilmis


def parse_tool_calls(text: str) -> EmulatedParse:
    """Kanonik çağrıları çıkar ve ham payload referanslarını çöz."""
    calls: list[ToolCall] = []
    errors: list[str] = []
    payloads: dict[str, str] = {}
    used_payloads: set[str] = set()

    # Kanonik ve eski biçim BİRLİKTE okunur: sözleşme değişse de yarıda kalmış bir
    # konuşmadaki blok ayrıştırılabilmelidir.
    for match in _payload_matches(text):
        payload_id = match.group("id")
        if payload_id in payloads:
            errors.append(f"yinelenen payload id: {payload_id}")
            continue
        try:
            body = _normalize_payload_body(match.group("body"))
            # Kontrol çerçeve TEMİZLENDİKTEN sonra yapılır: bakılan şey modelin
            # yazdığı içerik, taşımanın eklediği gürültü değil.
            _verify_payload_body(body, payload_id)
        except _PayloadResolutionError as error:
            # Bütünlük hataları payload kimliğini zaten taşır; çerçeve hataları taşımaz.
            detail = str(error)
            if not detail.startswith("payload "):
                detail = f"payload {payload_id}: {detail}"
            errors.append(detail)
            continue
        payloads[payload_id] = body

    without_payloads = _LEGACY_PAYLOAD_BLOCK.sub("", _PAYLOAD_BLOCK.sub("", text))
    # Kapanmamış blok tespiti HER İKİ biçimi de tanımalı: yalnızca kanonik işarete
    # bakmak, eski biçimde açılıp kapanmayan bir bloğu sessizce yok sayardı.
    if any(
        marker in without_payloads
        for marker in (PAYLOAD_OPEN, PAYLOAD_CLOSE, "<tool_payload", LEGACY_PAYLOAD_CLOSE)
    ):
        errors.append("kapanmamış veya geçersiz payload bloğu")

    for index, match in enumerate(_call_matches(without_payloads)):
        raw = match.group("body").strip()
        obj = _loads_tolerant(raw)
        if obj is None:
            errors.append(f"blok {index}: geçersiz JSON")
            continue
        if not isinstance(obj, dict):
            errors.append(f"blok {index}: çağrı bir JSON nesnesi olmalı")
            continue
        obj = _normalize_call_keys(obj)
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
        resolved = _apply_fence_strip(resolved)
        calls.append(
            ToolCall(
                id=f"emu-{index}",
                name=name.strip(),
                arguments=json.dumps(resolved, ensure_ascii=False),
            )
        )

    artan = sorted(set(payloads) - used_payloads)
    if artan and not calls:
        # Payload üretilmiş ama HİÇ çağrı yok: yanıt çağrı bloğuna varmadan kesilmiş.
        #
        # Ölçüldü (Gemini web): model dört dosyalık bir düzenlemeyi TEK yanıtta
        # toplamaya çalıştı, yanıt 5570 karakterde kesildi ve çağrı bloğu hiç
        # gelmedi. Genel "payload kullanılmadı" hatası bunu anlatmıyordu; model
        # ne olduğunu anlamayıp dosyanın TAMAMINI write_file ile yeniden yazmaya
        # düştü ve kodu bozdu. Teşhis burada net söylenir.
        errors.append(
            "Yanıtın araç çağrısı bloğuna varmadan kesildi: "
            f"{len(artan)} payload var ama {CALL_OPEN} bloğu yok. Yanıtı kısalt — "
            "bu yanıtta TEK bir araç çağrısı yap ve ötekileri sonraki turlara bırak. "
            "Dosyanın tamamını yeniden yazmaya KALKMA."
        )
    else:
        for payload_id in artan:
            errors.append(f"payload kullanılmadı: {payload_id}")

    outside = _LEGACY_BLOCK.sub("", _BLOCK.sub("", without_payloads))
    if any(marker in outside for marker in (CALL_OPEN, CALL_CLOSE, LEGACY_CALL_OPEN)):
        errors.append("kapanmamış veya eşleşmeyen araç çağrısı sınır işareti")

    return EmulatedParse(
        calls=tuple(calls),
        text=outside.strip(),
        errors=tuple(errors),
    )
