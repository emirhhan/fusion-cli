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

import json
import re
from dataclasses import dataclass

from ..core.constants import WEB_PROVIDER_SUFFIX

#: Düşünme bloğunu sarmalayan etiket adları (L1-03). Zayıf/farklı modeller `<think>`
#: yerine `<thinking>`, `<thought>` ya da `<reasoning>` yazar; büyük/küçük harf fark etmez.
THINK_TAG_NAMES = ("thinking", "think", "thought", "reasoning")
_TAG_ALTERNATION = "|".join(THINK_TAG_NAMES)
_OPEN_TAG = re.compile(rf"<({_TAG_ALTERNATION})>", re.IGNORECASE)
_CLOSE_TAG = re.compile(rf"</({_TAG_ALTERNATION})>", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Segment:
    """Metnin bir parçası ve düşünme (`<think>…`) içeriği olup olmadığı."""

    is_thinking: bool
    text: str


def segment(text: str, *, streaming: bool = False) -> list[Segment]:
    """Metni SIRAYLA görünür ve düşünme parçalarına ayır (tek gramer kaynağı).

    Hem gizleme (`strip_thinking`) hem gösterme (görünür thinking bloğu) bu tek
    ayrıştırmadan beslenir; etiket grameri iki ayrı yerde tekrar edilmez.

    `streaming=True` iken sondaki, bir etiketin yarısı olabilecek parça geri tutulur:
    ne `<th` ekrana sızar ne de `</thi`. Akış bitince `streaming=False` ile çağır;
    geri tutulan varsa serbest bırakılır.

    Kapanışsız açılış (L1-03): tamamlanmış metinde, açılıştan ÖNCE görünür cevap metni
    varsa model cevabın içinde etiketi sözcük olarak yazmıştır (kod örneği, açıklama);
    kalan metin cevabın parçasıdır ve atılmaz. Metin doğrudan kapanışsız bir açılışla
    başlıyorsa bu kesilmiş düşünmedir (token sınırı) ve gizli kalır. Akış sürerken
    karar verilemez, sonrası tutulur.
    """
    segments: list[Segment] = []
    index = 0
    total = len(text)
    open_name: str | None = None
    # Açılışı olmayan kapanış: bazı modeller `<think>` yazmadan düşünür ve yalnız
    # `</think>` ile bitirir. Ölçüldü (26 Eylül, gemini_web): "The blog site is
    # complete… Let me provide a summary.</think>Tamamlandı…" kullanıcıya
    # olduğu gibi gösteriliyordu. Kapanıştan önceki her şey düşünmedir.
    # Akış sırasında karar verilemez (kapanış henüz gelmemiş olabilir); yalnız
    # tamamlanmış metinde uygulanır.
    first_close = _CLOSE_TAG.search(text)
    first_open = _OPEN_TAG.search(text)
    if (
        not streaming
        and first_close is not None
        and (first_open is None or first_close.start() < first_open.start())
    ):
        _append(segments, True, text[: first_close.start()])
        index = first_close.end()
    while index < total:
        if open_name is None:
            found = _OPEN_TAG.search(text, index)
        else:
            found = re.compile(rf"</{open_name}>", re.IGNORECASE).search(text, index)
        if found is not None:
            _append(segments, open_name is not None, text[index : found.start()])
            index = found.end()
            open_name = found.group(1) if open_name is None else None
            continue
        rest = text[index:]
        if streaming:
            # Aradığımız etiketin yarısı sonda kalmış olabilir (`<th`, `</thi`); geri tut.
            pending = _pending_tag_length(rest, open_name)
            if pending:
                rest = rest[:-pending]
        elif open_name is not None and _has_visible_text(segments):
            # Kapanışsız açılış, öncesinde görünür cevap varsa etiket sözcüktür; metni sakla.
            _append(segments, False, text[index - len(open_name) - 2 : index] + rest)
            break
        _append(segments, open_name is not None, rest)
        break
    return segments


def _has_visible_text(segments: list[Segment]) -> bool:
    """Şimdiye dek ayrılan parçalar arasında görünür (düşünme olmayan) metin var mı?"""
    return any(not part.is_thinking and part.text.strip() for part in segments)


def strip_thinking(text: str, *, streaming: bool = False) -> str:
    """Görünür metni düşünme bloklarından arındır (tek gramer: `segment`)."""
    return "".join(part.text for part in segment(text, streaming=streaming) if not part.is_thinking)


def _append(segments: list[Segment], is_thinking: bool, text: str) -> None:
    """Boş olmayan parçayı listeye ekle."""
    if text:
        segments.append(Segment(is_thinking=is_thinking, text=text))


def _pending_tag_length(text: str, open_name: str | None) -> int:
    """Metnin sonundaki, aranan etiketin başlangıcı olabilecek parçanın uzunluğu.

    Düşünme dışındayken tüm açılış etiketleri (`<think>`, `<thinking>`…), içindeyken
    açık olanın kapanışı aranır; büyük/küçük harf duyarsızdır.
    """
    tags = (
        [f"<{name}>" for name in THINK_TAG_NAMES]
        if open_name is None
        else [f"</{open_name.lower()}>"]
    )
    lowered = text.lower()
    longest = 0
    for tag in tags:
        for length in range(min(len(tag) - 1, len(text)), 0, -1):
            if lowered.endswith(tag[:length]):
                longest = max(longest, length)
                break
    return longest


#: Bu sürenin altındaki ölçümler milisaniye olarak gösterilir.
_MS_THRESHOLD = 1_000
#: Hata özetinde gösterilecek en fazla karakter. 80 sütunluk bir terminalde
#: önekle birlikte tek satıra sığacak şekilde seçilmiştir.
ERROR_SUMMARY_CHARS = 60
#: Sağlayıcı JSON gövdesindeki açıklama alanı.
#: Kaçışlı tırnaklar (`\"`) açıklamayı erken kesmez: `[^"]` yerine `(?:[^"\\]|\\.)` (L1-42).
_JSON_MESSAGE = re.compile(r'"message"\s*:\s*"((?:[^"\\]|\\.){3,200})"')


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

    Tarayıcı tabanlı sağlayıcılarda ORTA parça atılmaz: orası satıcı adı değil
    HESAP adıdır (`gemini_web/isimdijital/auto`). Ölçüldü — kullanıcı satırdaki
    `gemini_web/auto` ifadesini ayrı bir sağlayıcı sandı ve kendi hesabının
    kullanılmadığını düşündü. Hangi hesapla çalışıldığı, birden çok hesabı olan
    kullanıcı için tam da görülmesi gereken bilgidir.
    """
    parcalar = model_id.split("/")
    if len(parcalar) < 2:
        return model_id
    if parcalar[0].endswith(WEB_PROVIDER_SUFFIX):
        # `gemini_web/isimdijital/auto` → `gemini_web/isimdijital`: son parça web
        # oturumlarında her zaman "auto"dur ve hiçbir şey söylemez.
        return "/".join(parcalar[:2])
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
    if not match:
        return ""
    try:
        return str(json.loads(f'"{match.group(1)}"')).strip()  # \" ve \n kaçışlarını çöz
    except ValueError:
        return match.group(1).strip()


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
