"""Kayan pencere maskeleme: eski araç sonuçları modele giden görünümde yer tutucuya iner.

`history.clear_old_tool_outputs` yalnız sıkıştırma EŞİĞİNDE (≈177.000 karakter) çalışır;
bu modül eşik beklemeden, her model çağrısından önce çalışır. Kanıt: JetBrains (arXiv
2508.21433) eski gözlemleri gizlemenin LLM özetlemesi kadar iyi ve ~%50 ucuz olduğunu,
SWE-agent son ~5 gözlemi tam tutmanın tam geçmişten iyi olduğunu ölçtü. Manus'un dersi
korunur: HATALAR bağlamda kalır.

Tasarım:

- **Yalnız görünüm.** Girdi liste ve mesajlar değişmez; `mask_view` yeni bir liste döner.
  Kalıcı geçmiş (oturum kaydı, arayüz, yeniden oynatma) tam kalır.
- **Korunanlar.** Son `window` araç sonucu; son araç çağıran assistant mesajından
  SONRAKİ tüm sonuçlar (paralel çağrılar, A1-01); hatalar (`ok is False`);
  `MIN_MASK_CHARS`'tan kısa sonuçlar; kullanıcıya sorulan soruların / öğretmenin / alt
  ajanların / derslerin / plan ve yapılacaklar listesinin sonuçları; kural dosyası
  okumaları. `user` mesajları (kurallar, özetler) bu modülün kapsamında DEĞİLDİR.
- **Önek kararlılığı.** Maskelenen mesaj `MaskLedger`'a yazılır; açık kanıt pini
  geçici olarak sınırlı özgün içeriği gösterir, pin bırakılınca maske geri gelir.
  Yer tutucu mesajın kendisinden belirlenir (aynı girdi, aynı metin). Pencere
  her turda 1 mesaj kaymaz: sonuçlar `batch_size(window)` kadar birikince TOPLU
  maskelenir, böylece sağlayıcı önbelleği her çağrıda değil birkaç çağrıda bir bozulur.
  Model bu yüzden `window` ile `window + batch_size - 1` arası tam sonuç görür.
"""

from __future__ import annotations

import json
import re
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePath

from ...core.types import Message, ToolCall
from .history import (
    CLEARED_TOOL_OUTPUT,
    PIN_MAX_CHARS,
    pin_tool_output,
    total_chars,
    unseen_tool_indexes,
)

#: Yer tutucunun başlığı; yeniden maskelemeyi önler ve testlerde tanıma işaretidir.
MASK_PREFIX = "[eski araç çıktısı gizlendi"
#: Bundan kısa sonuç maskelenmez: yer tutucu da yaklaşık bu kadar yer tutar.
MIN_MASK_CHARS = 400
#: Argüman özetinin üst sınırı ve tek değerin üst sınırı (karakter).
ARGS_SUMMARY_CHARS = 140
ARGS_VALUE_CHARS = 60
#: Defter bu çarpanı aşarsa artık listede olmayan mesajlar atılır.
LEDGER_PRUNE_FACTOR = 2

#: Sonucu hiçbir zaman maskelenmeyen araçlar: çıktıları yeniden üretilemez ya da
#: kullanıcıdan / öğretmenden / alt ajandan gelen bilgidir.
#: `Skill`: çağrılan becerinin gövdesi sonraki turlarda da bağlamda kalır (#139, #140).
EXEMPT_TOOLS = frozenset(
    {"ask_user", "ask_teacher", "spawn_agents", "recall_lessons", "todo_write", "plan", "Skill"}
)
#: Proje / kullanıcı kuralı taşıyan dosyalar (yol sonu, küçük harf): okumaları maskelenmez.
RULE_FILE_NAMES = frozenset(
    {
        "claude.md",
        "agents.md",
        "rules.md",
        "gemini.md",
        ".cursorrules",
        "copilot-instructions.md",
        "fusion.md",
    }
)
#: Argüman özetinde önce gösterilecek anahtarlar.
_KEY_ARGUMENTS = ("path", "file_path", "command", "query", "url", "pattern", "name")
#: `core.artifacts.offload_output` metnindeki yol satırı; biçim değişirse test düşer.
_ARTIFACT_PATH = re.compile(r"dosyaya alındı: (.+)")


def batch_size(window: int) -> int:
    """Kaç sonuç birikince toplu maskeleneceği: pencerenin yarısı (en az 1)."""
    return max(1, window // 2)


@dataclass(slots=True)
class MaskLedger:
    """Maskelenmiş mesajların defteri (kimlikle); bir kez maskelenen eski haline dönmez.

    Mesaj nesnesine referans tutulur: `id()` nesne yaşadıkça geçerlidir. Oturum
    kaydından yeniden yüklenen mesajlar yeni nesnedir; defter tur başına kurulur.
    """

    entries: dict[int, Message] = field(default_factory=dict)
    #: Maskelenmiş sonuçların `tool_call_id`'leri (tekrar kapısı için, bkz. `note_call`).
    masked_call_ids: set[str] = field(default_factory=set)
    #: Çağrı imzası -> o imzayla yapılan SON çağrının kimliği.
    last_call: dict[Hashable, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, message: Message) -> bool:
        return id(message) in self.entries

    def add(self, messages: Sequence[Message]) -> None:
        for message in messages:
            self.entries[id(message)] = message
            if message.tool_call_id:
                self.masked_call_ids.add(message.tool_call_id)

    def note_call(self, signature: Hashable, call_id: str) -> bool:
        """Çağrıyı kaydet; bu imzanın önceki sonucu MASKELENMİŞSE True dön (bir kez).

        Yer tutucu modele "gerekirse yeniden çalıştır/oku" der; tekrar kapısı bu meşru
        yeniden isteği "zaten yaptın" diye önbellek notuyla ya da engelle karşılamamalı.
        Çağıran True alınca imzanın sayacını sıfırlar. Yeni sonuç taze olduğundan
        yeniden maskelenirse yeni bir çağrı kimliğiyle yine bir kez bağışlanır.
        """
        onceki = self.last_call.get(signature)
        self.last_call[signature] = call_id
        if onceki is not None and onceki in self.masked_call_ids:
            self.masked_call_ids.discard(onceki)
            return True
        return False

    def prune(self, live: Sequence[Message]) -> None:
        """Artık geçmişte olmayan (sıkıştırmayla atılan) kayıtları bırak."""
        if len(self.entries) <= LEDGER_PRUNE_FACTOR * len(live) + 64:
            return
        canli = {id(message) for message in live}
        self.entries = {key: value for key, value in self.entries.items() if key in canli}


@dataclass(frozen=True, slots=True)
class MaskView:
    """Modele gidecek görünüm ve ölçümü."""

    messages: list[Message]
    #: Görünümdeki toplam maskeli sonuç.
    masked: int = 0
    #: Bu çağrıda YENİ maskelenen (önek kayması olan) sonuç.
    newly_masked: int = 0
    #: Kazanılan karakter (`total_chars` farkı: içerik + görsel payı).
    saved_chars: int = 0


def mask_view(
    messages: Sequence[Message],
    window: int,
    ledger: MaskLedger,
    *,
    commit: bool = True,
    pinned_call_ids: frozenset[str] = frozenset(),
    pin_chars: int = PIN_MAX_CHARS,
) -> MaskView:
    """Eski araç sonuçlarını yer tutucuya indirmiş bir görünüm üret; girdiye dokunma.

    `commit=False` yalnız ölçer (defteri değiştirmez): sıkıştırma kararından önce
    görünümün boyutunu öğrenmek için.
    """
    if window <= 0:
        return MaskView(list(messages))
    araclar = [i for i, m in enumerate(messages) if m.role == "tool"]
    if len(araclar) <= window:
        return MaskView(list(messages))
    unseen = unseen_tool_indexes(messages)
    pins = {i for i in araclar if messages[i].tool_call_id in pinned_call_ids} - unseen
    korunan = set(araclar[-window:]) | unseen | pins
    cagrilar = _paired_calls(messages)
    adaylar = [i for i in araclar if i not in korunan and _maskable(messages[i], cagrilar.get(i))]
    bekleyen = [i for i in adaylar if messages[i] not in ledger]
    yeni = bekleyen if len(bekleyen) >= batch_size(window) else []
    maskeli = {i for i in adaylar if messages[i] in ledger} | set(yeni)
    gorunum = list(messages)
    for index in pins:
        gorunum[index] = pin_tool_output(messages[index], pin_chars)
    for i in maskeli:
        gorunum[i] = _masked_message(messages[i], cagrilar.get(i))
    if commit and yeni:
        ledger.add([messages[i] for i in yeni])
        ledger.prune(messages)
    return MaskView(
        gorunum,
        masked=len(maskeli),
        newly_masked=len(yeni),
        saved_chars=total_chars(messages) - total_chars(gorunum),
    )


def _paired_calls(messages: Sequence[Message]) -> dict[int, ToolCall]:
    """Her `tool` mesajının indeksini, en yakın önceki assistant'ın aynı kimlikli çağrısına eşle."""
    eslesme: dict[int, ToolCall] = {}
    guncel: dict[str, ToolCall] = {}
    for index, message in enumerate(messages):
        if message.role == "assistant" and message.tool_calls:
            guncel = {call.id: call for call in message.tool_calls}
        elif message.role == "tool" and message.tool_call_id in guncel:
            eslesme[index] = guncel[message.tool_call_id]
    return eslesme


def _maskable(message: Message, call: ToolCall | None) -> bool:
    if message.ok is False:
        return False
    if message.name in EXEMPT_TOOLS:
        return False
    if message.content.startswith((MASK_PREFIX, CLEARED_TOOL_OUTPUT.split("(")[0])):
        return False
    if len(message.content) < MIN_MASK_CHARS and not message.images:
        return False
    return not _reads_rule_file(call)


def _reads_rule_file(call: ToolCall | None) -> bool:
    if call is None:
        return False
    veri = _parse(call.arguments)
    for anahtar in ("path", "file_path"):
        deger = veri.get(anahtar)
        if isinstance(deger, str) and PurePath(deger).name.lower() in RULE_FILE_NAMES:
            return True
    return False


def _parse(arguments: str) -> dict[str, object]:
    try:
        veri = json.loads(arguments)
    except ValueError:
        return {}
    return veri if isinstance(veri, dict) else {}


def _args_summary(call: ToolCall | None) -> str:
    if call is None:
        return ""
    veri = _parse(call.arguments)
    if not veri:
        return call.arguments[:ARGS_VALUE_CHARS]
    sirali = [k for k in _KEY_ARGUMENTS if k in veri] + [k for k in veri if k not in _KEY_ARGUMENTS]
    parcalar: list[str] = []
    for anahtar in sirali:
        deger = veri[anahtar]
        if not isinstance(deger, (str, int, float, bool)):
            continue
        metin = str(deger).replace("\n", " ")
        if len(metin) > ARGS_VALUE_CHARS:
            metin = metin[: ARGS_VALUE_CHARS - 1] + "…"
        parcalar.append(f"{anahtar}={metin}")
        if len(parcalar) == 3:
            break
    return ", ".join(parcalar)[:ARGS_SUMMARY_CHARS]


def _masked_message(message: Message, call: ToolCall | None) -> Message:
    """Yer tutucu: yalnız mesajın kendisinden ve eşli çağrıdan türer (deterministik)."""
    ad = message.name or (call.name if call is not None else "araç")
    durum = "başarılı" if message.ok else "durum bilinmiyor"
    boyut = f"{len(message.content):,}".replace(",", ".")
    parcalar = [f"{ad}({_args_summary(call)})", durum, f"{boyut} karakter"]
    if message.images:
        parcalar.append(f"{len(message.images)} görsel")
    yol = _ARTIFACT_PATH.search(message.content)
    if yol is not None:
        parcalar.append(f"tam çıktı diskte: {yol.group(1).strip()}")
    parcalar.append("gerekirse aracı yeniden çalıştır ya da dosyayı oku")
    return replace(message, content=f"{MASK_PREFIX} · {' · '.join(parcalar)}]", images=())
