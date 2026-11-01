"""Çağrılan becerinin sonraki turlarda bağlamda kalması (Claude Code #140).

Claude Code (code.claude.com/docs/en/skills, "Skill content lifecycle"): işlenmiş SKILL.md
tek mesaj olarak konuşmaya girer ve sonraki turlarda da kalır; dosya yeniden okunmaz.
Sıkıştırmadan sonra her becerinin EN SON çağrısı özetin ardından yeniden eklenir: beceri başına
ilk 5.000 token, hepsi birlikte 25.000 token; çok beceri çağrılmışsa eskiler düşebilir.

Fusion'da iki yol var:

- Kullanıcının `/ad` gövdesi turun sistem ekine girer (konuşma geçmişine yazılmaz). Bu kayıt
  gövdeyi sonraki her tura TAM taşır; sıkıştırma olunca 5k/25k sınırına iner.
- Modelin `Skill` aracıyla yüklediği gövde araç sonucu olarak geçmişte zaten durur (maskelenmez,
  diske alınmaz; #139). Taşınmaz; sıkıştırma ya da eşik temizliği sonucu geçmişten düşürünce
  5k/25k sınırıyla yeniden eklenir.

Sıkıştırma, geçmişteki özet mesajının (`[önceki konuşmanın özeti]`) değişmesinden anlaşılır;
REPL `/compact`, otomatik özetleme ve masaüstü aynı izi bırakır. Sohbet kimliği değişince
(`/resume`, masaüstünde başka sohbet) ve `/clear` ile kayıt sıfırlanır.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from ...core.types import Message
from .history import CLEARED_TOOL_OUTPUT, CONVERSATION_SUMMARY_PREFIX, STEPS_SUMMARY_PREFIX

#: Beceri başına yeniden eklenen en çok token (Claude Code: 5.000).
PER_SKILL_TOKENS = 5_000
#: Yeniden eklenen becerilerin toplam bütçesi (Claude Code: 25.000).
TOTAL_TOKENS = 25_000
#: Token tahmini: karakter / 4 (sağlayıcıdan bağımsız kaba ölçü).
CHARS_PER_TOKEN = 4
#: Modelin beceri aracı (`skill_tool.SKILL_TOOL_NAME`; döngüsel içe aktarmayı önlemek için yazılı).
SKILL_TOOL = "Skill"

CARRIED_HEADER = (
    "Bu sohbette daha önce çağrılan beceriler (her birinin son çağrısı); yönergeleri "
    "geçerliliğini korur:"
)
TRUNCATED_NOTE = "\n[… beceri gövdesinin kalanı bağlam bütçesi nedeniyle eklenmedi]"
_CLEARED_HEAD = CLEARED_TOOL_OUTPUT.split("(")[0]


@dataclass(frozen=True, slots=True)
class SkillEntry:
    """Bir becerinin son çağrısı: gövde, aracın çağrı kimliği (`/ad` için boş), sınır durumu."""

    name: str
    body: str
    call_id: str = ""
    #: Sıkıştırma ya da temizlik gövdeyi geçmişten düşürdü: 5k/25k sınırıyla eklenir.
    capped: bool = False


@dataclass(frozen=True, slots=True)
class InvokedSkills:
    """Bir sohbette çağrılan becerilerin son gövdeleri (eskiden yeniye)."""

    conversation_id: str = ""
    entries: tuple[SkillEntry, ...] = field(default=())
    #: Geçmişte son görülen özet mesajının izi; değişirse sıkıştırma olmuştur.
    compaction_mark: str = ""
    #: Kaydedilmiş `Skill` çağrı kimlikleri (aynı sonuç yeniden eklenmesin).
    seen_calls: frozenset[str] = field(default=frozenset())

    def for_conversation(self, conversation_id: str) -> InvokedSkills:
        """Başka sohbete geçildiyse boş kayıt; aynıysa kendisi."""
        if conversation_id == self.conversation_id:
            return self
        return InvokedSkills(conversation_id)

    def remember(self, name: str, body: str, call_id: str = "") -> InvokedSkills:
        """Aynı becerinin önceki çağrısını düşür, yenisini sona ekle."""
        if not body.strip():
            return self
        kept = tuple(entry for entry in self.entries if entry.name != name)
        seen = self.seen_calls | {call_id} if call_id else self.seen_calls
        return replace(self, entries=(*kept, SkillEntry(name, body, call_id)), seen_calls=seen)

    def compacted(self) -> InvokedSkills:
        """Bağlam özetlendi: kayıtlı her çağrı artık 5k/25k sınırıyla yeniden eklenir."""
        return replace(self, entries=tuple(replace(e, capped=True) for e in self.entries))

    def observe(self, history: Sequence[Message]) -> InvokedSkills:
        """Geçmişe bak: sıkıştırmayı, yeni ve geçmişten düşmüş `Skill` sonuçlarını işle."""
        record = self
        mark = _compaction_mark(history)
        if mark and mark != record.compaction_mark:
            record = replace(record.compacted(), compaction_mark=mark)
        live = _live_skill_results(history)
        for call_id, (name, body) in live.items():
            if call_id not in record.seen_calls:
                record = record.remember(name, body, call_id)
        entries = tuple(
            replace(entry, capped=True)
            if entry.call_id and entry.call_id not in live and not entry.capped
            else entry
            for entry in record.entries
        )
        return replace(record, entries=entries)

    def carried_block(self, exclude: str | tuple[str, ...] = "") -> str:
        """Sonraki tura taşınan blok, en yeni önce.

        Geçmişte duran `Skill` sonucu taşınmaz; sıkıştırılmamış `/ad` gövdesi tam gider;
        sıkıştırmadan sonra beceri başına 5k, toplam 25k token.
        """
        remaining = TOTAL_TOKENS * CHARS_PER_TOKEN
        per_skill = PER_SKILL_TOKENS * CHARS_PER_TOKEN
        excluded = {exclude} if isinstance(exclude, str) else set(exclude)
        parts: list[str] = []
        for entry in reversed(self.entries):
            if entry.name in excluded or (entry.call_id and not entry.capped):
                continue
            if not entry.capped:
                parts.append(entry.body)
                continue
            if remaining <= 0:
                continue
            limit = min(per_skill, remaining)
            body = entry.body
            parts.append(body if len(body) <= limit else body[:limit] + TRUNCATED_NOTE)
            remaining -= min(len(body), limit)
        return "\n\n".join((CARRIED_HEADER, *parts)) if parts else ""


def _compaction_mark(history: Sequence[Message]) -> str:
    for message in reversed(history):
        if message.role == "user" and message.content.startswith(
            (CONVERSATION_SUMMARY_PREFIX, STEPS_SUMMARY_PREFIX)
        ):
            return hashlib.sha256(message.content.encode("utf-8")).hexdigest()[:16]
    return ""


def _live_skill_results(history: Sequence[Message]) -> dict[str, tuple[str, str]]:
    """Geçmişte tam duran başarılı `Skill` sonuçları: çağrı kimliği → (beceri adı, gövde)."""
    names: dict[str, str] = {}
    live: dict[str, tuple[str, str]] = {}
    for message in history:
        if message.role == "assistant":
            for call in message.tool_calls:
                if call.name == SKILL_TOOL:
                    names[call.id] = _skill_name(call.arguments)
        elif message.role == "tool" and message.name == SKILL_TOOL and message.ok is not False:
            call_id = message.tool_call_id or ""
            name = names.get(call_id, "")
            if name and call_id and not message.content.startswith(_CLEARED_HEAD):
                live[call_id] = (name, message.content)
    return live


def _skill_name(arguments: str) -> str:
    try:
        data = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return ""
    value = data.get("skill", "") if isinstance(data, dict) else ""
    return str(value).strip().lstrip("/")
