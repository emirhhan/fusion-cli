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

THINK_OPEN = "<think>"
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str, *, streaming: bool = False) -> str:
    """Görünür metni düşünme bloklarından arındır.

    `streaming=True` iken, tamamlanmamış bir açılış etiketi olabilecek son parça da
    geri tutulur. Akış bittiğinde `streaming=False` ile çağır: geri tutulan varsa
    serbest bırakılır.
    """
    visible = _THINK_BLOCK.sub("", text)
    opening = visible.find(THINK_OPEN)
    if opening != -1:
        return visible[:opening]
    if streaming:
        pending = _pending_open_length(visible)
        if pending:
            return visible[:-pending]
    return visible


def _pending_open_length(text: str) -> int:
    """Metnin sonundaki, `<think>` etiketinin başlangıcı olabilecek parçanın uzunluğu."""
    for length in range(min(len(THINK_OPEN) - 1, len(text)), 0, -1):
        if text.endswith(THINK_OPEN[:length]):
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
