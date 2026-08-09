"""Görüntülenecek metin üzerinde saf dönüşümler.

Reasoning modelleri cevaptan önce "düşünme" metni üretir ve bunu `<think>…</think>`
bloklarına sarar. Bu metin kullanıcıya gösterilmemelidir: hem çok uzundur hem de
cevabın kendisi değildir.

Akışta ayıklama iki yerde zorlaşır ve ikisi de burada ele alınır:

1. **Kapanmamış açılış** — `<think>` görüldüğünde kapanışı henüz gelmemiştir.
   Sonrası geri tutulur; kapanış gelince zaten atılacaktır.
2. **Yarım açılış etiketi** — parça `"<th"` olarak gelebilir. Bu da geri tutulur,
   yoksa etiketin başı ekrana sızar. Tur bitince (`streaming=False`) geri tutulan
   parça serbest bırakılır: gerçekten `<` ile biten bir cevap kaybolmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


@dataclass(frozen=True, slots=True)
class Segment:
    """Metnin bir parçası ve düşünme (`<think>…`) içeriği olup olmadığı."""

    is_thinking: bool
    text: str


def segment(text: str, *, streaming: bool = False) -> list[Segment]:
    """Metni SIRAYLA görünür ve düşünme parçalarına ayır (tek gramer kaynağı).

    Hem gizleme (`strip_thinking`) hem gösterme (görünür thinking bloğu) bu tek
    ayrıştırmadan beslenir; `<think>`/`</think>` grameri iki ayrı yerde tekrar edilmez.

    `streaming=True` iken sondaki, bir etiketin yarısı olabilecek parça geri tutulur:
    ne `<th` ekrana sızar ne de `</thi`. Akış bitince `streaming=False` ile çağır;
    geri tutulan varsa serbest bırakılır.
    """
    segments: list[Segment] = []
    index = 0
    total = len(text)
    in_thinking = False
    while index < total:
        tag = THINK_CLOSE if in_thinking else THINK_OPEN
        found = text.find(tag, index)
        if found != -1:
            _append(segments, in_thinking, text[index:found])
            index = found + len(tag)
            in_thinking = not in_thinking
            continue
        rest = text[index:]
        if streaming:
            # Aradığımız etiketin yarısı sonda kalmış olabilir (`<th`, `</thi`); geri tut.
            pending = _pending_tag_length(rest, tag)
            if pending:
                rest = rest[:-pending]
        _append(segments, in_thinking, rest)
        break
    return segments


def strip_thinking(text: str, *, streaming: bool = False) -> str:
    """Görünür metni düşünme bloklarından arındır (tek gramer: `segment`)."""
    return "".join(part.text for part in segment(text, streaming=streaming) if not part.is_thinking)


def _append(segments: list[Segment], is_thinking: bool, text: str) -> None:
    """Boş olmayan parçayı listeye ekle."""
    if text:
        segments.append(Segment(is_thinking=is_thinking, text=text))


def _pending_tag_length(text: str, tag: str) -> int:
    """Metnin sonundaki, `tag` etiketinin başlangıcı olabilecek parçanın uzunluğu."""
    for length in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:length]):
            return length
    return 0


#: Bu sürenin altındaki ölçümler milisaniye olarak gösterilir.
_MS_THRESHOLD = 1_000
#: Hata özetinde gösterilecek en fazla karakter. 80 sütunluk bir terminalde
#: önekle birlikte tek satıra sığacak şekilde seçilmiştir.
ERROR_SUMMARY_CHARS = 60
#: Sağlayıcı JSON gövdesindeki açıklama alanı.
_JSON_MESSAGE = re.compile(r'"message"\s*:\s*"([^"]{3,200})"')


def format_duration(milliseconds: int) -> str:
    """Süreyi insan ölçeğinde yaz: 840ms, 2.9s, 1m12s."""
    if milliseconds < _MS_THRESHOLD:
        return f"{milliseconds}ms"
    seconds = milliseconds / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m{remainder:02d}s"


def format_model(model_id: str) -> str:
    """Model kimliğini ekrana sığacak biçime indir: `<sağlayıcı>/<model adı>`.

    LiteLLM kimlikleri üç parçalı olabiliyor (`nvidia_nim/nvidia/nemotron-3-super-…`)
    ve aradaki satıcı adı ekranda yer kaplamaktan başka bir şey yapmıyor.

    Sağlayıcı öneki KORUNUR ve bu önemlidir: yedek zinciri çoğu zaman AYNI modelin
    başka bir sağlayıcıdaki kopyasıdır (`openrouter/nvidia/…:free`). Yalnızca son
    parça gösterilseydi yedeğe düşmüş bir tur, birincille aynı görünürdü.
    """
    parcalar = model_id.split("/")
    if len(parcalar) < 2:
        return model_id
    return f"{parcalar[0]}/{parcalar[-1]}"


#: İstenen kimlik ile gözlenen kademe arasındaki ayırıcı.
SERVED_BY_SEPARATOR = " · "


def format_served_model(model_id: str, served_by: str = "") -> str:
    """Ekrana istenen kimliği, biliniyorsa GÖZLENEN kademeyle birlikte yaz.

    Tarayıcı taşımasında bu ikisi ayrışabilir: istek `gemini_web/auto` der ama
    cevabı hesabın arayüzde seçili kademesi yazar. Ölçüldü: oturumu düşmüş bir
    profille yapılan koşuda cevabı anonim "Flash-Lite" kademesi yazdı, ekranda
    ise yalnızca `gemini_web/auto` görünüyordu — kullanıcının kendi hesabının
    gücüyle çalıştığını sanması için hiçbir engel yoktu.

    Kademe bilinmiyorsa satır DEĞİŞMEZ: uydurulmuş bir kademe, kademe
    yokluğundan kötüdür.
    """
    etiket = format_model(model_id)
    kademe = served_by.strip()
    if not kademe or kademe in etiket:
        return etiket
    return f"{etiket}{SERVED_BY_SEPARATOR}{kademe}"


def summarize_error(error: str) -> str:
    """Sağlayıcı hatasını tek satırlık okunur bir özete indir.

    Ham hatalar üç ayrı gürültü kaynağı taşır ve ekranı kaplar:

    - JSON gövdesi, HTTP başlıkları ve yeniden deneme sayacı,
    - SDK'nın sardığı katmanlar yüzünden TEKRARLANAN hata sınıfı adı
      (`RateLimitError: litellm.RateLimitError: RateLimitError: …`),
    - modül önekleri (`litellm.`).

    Üçü de burada temizlenir; kalan bilgi kullanıcının ihtiyaç duyduğudur.
    """
    flat = " ".join(error.split())
    chain = _dedupe_segments(_cut_at_noise(flat))
    # Asıl açıklama çoğu zaman atacağımız JSON gövdesinin içindedir. Varsa onu
    # kullanırız ve aradaki sağlayıcı istisna adlarını atarız: kullanıcıya
    # "OpenrouterException" değil, ne olduğu lazım.
    detail = _extract_message(flat)
    if not detail:
        return _shorten(chain)
    error_class = chain.split(":", 1)[0].strip()
    return _shorten(f"{error_class} · {detail}" if error_class else detail)


def _extract_message(text: str) -> str:
    """Sağlayıcının JSON gövdesindeki insan-okunur açıklamayı çıkar."""
    match = _JSON_MESSAGE.search(text)
    return match.group(1).strip() if match else ""


def _cut_at_noise(text: str) -> str:
    """Yapılandırılmış gürültünün başladığı yerden itibaren at."""
    for marker in ("LiteLLM Retried", " {", " - {"):
        position = text.find(marker)
        if position > 0:
            text = text[:position]
    return text.strip(" -")


def _dedupe_segments(text: str) -> str:
    """`A: litellm.A: A: B` → `A: B`. Modül öneki atılır, tekrarlar teke iner."""
    segments: list[str] = []
    seen: set[str] = set()
    for raw in text.split(": "):
        segment = _strip_module_prefix(raw.strip())
        if not segment:
            continue
        key = segment.lower()
        if key in seen:
            continue
        seen.add(key)
        segments.append(segment)
    return ": ".join(segments)


def _strip_module_prefix(segment: str) -> str:
    """`litellm.RateLimitError` → `RateLimitError`.

    Yalnızca noktalı TEK BİR tanımlayıcıya uygulanır; boşluk içeren bir parça
    cümledir ve içindeki nokta modül ayracı değildir.
    """
    if " " in segment or "." not in segment:
        return segment
    return segment.rsplit(".", 1)[-1]


def _shorten(text: str) -> str:
    if len(text) <= ERROR_SUMMARY_CHARS:
        return text
    return text[: ERROR_SUMMARY_CHARS - 1] + "…"
