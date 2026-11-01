"""Çağrılan becerinin sonraki turlarda bağlamda kalması (Claude Code #140).

Claude Code (code.claude.com/docs/en/skills, "Skill content lifecycle"): işlenmiş SKILL.md
tek mesaj olarak konuşmaya girer ve sonraki turlarda da kalır; dosya yeniden okunmaz.
Sıkıştırmadan sonra her becerinin EN SON çağrısı özetin ardından yeniden eklenir: beceri başına
ilk 5.000 token, hepsi birlikte 25.000 token; çok beceri çağrılmışsa eskiler düşebilir.

Fusion'da `/ad` gövdesi turun sistem ekine girer. Bu modül sohbet başına son çağrıları tutar
ve sonraki her turun ekine aynı bütçeyle yeniden koyar: geçmiş sıkıştırılsa da gövde kaybolmaz.
Sohbet kimliği değişince (`/resume`, masaüstünde başka sohbet) ve `/clear` ile sıfırlanır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Beceri başına yeniden eklenen en çok token (Claude Code: 5.000).
PER_SKILL_TOKENS = 5_000
#: Yeniden eklenen becerilerin toplam bütçesi (Claude Code: 25.000).
TOTAL_TOKENS = 25_000
#: Token tahmini: karakter / 4 (sağlayıcıdan bağımsız kaba ölçü).
CHARS_PER_TOKEN = 4

CARRIED_HEADER = (
    "Bu sohbette daha önce çağrılan beceriler (her birinin son çağrısı); yönergeleri "
    "geçerliliğini korur:"
)
TRUNCATED_NOTE = "\n[… beceri gövdesinin kalanı bağlam bütçesi nedeniyle eklenmedi]"


@dataclass(frozen=True, slots=True)
class InvokedSkills:
    """Bir sohbette çağrılan becerilerin son gövdeleri (eskiden yeniye)."""

    conversation_id: str = ""
    bodies: tuple[tuple[str, str], ...] = field(default=())

    def for_conversation(self, conversation_id: str) -> InvokedSkills:
        """Başka sohbete geçildiyse boş kayıt; aynıysa kendisi."""
        if conversation_id == self.conversation_id:
            return self
        return InvokedSkills(conversation_id)

    def remember(self, name: str, body: str) -> InvokedSkills:
        """Aynı becerinin önceki çağrısını düşür, yenisini sona ekle."""
        if not body.strip():
            return self
        kept = tuple(pair for pair in self.bodies if pair[0] != name)
        return InvokedSkills(self.conversation_id, (*kept, (name, body)))

    def carried_block(self, exclude: str = "") -> str:
        """Sonraki tura taşınan blok: en yeni önce, beceri başına 5k, toplam 25k token."""
        remaining = TOTAL_TOKENS * CHARS_PER_TOKEN
        per_skill = PER_SKILL_TOKENS * CHARS_PER_TOKEN
        parts: list[str] = []
        for name, body in reversed(self.bodies):
            if name == exclude or remaining <= 0:
                continue
            limit = min(per_skill, remaining)
            text = body if len(body) <= limit else body[:limit] + TRUNCATED_NOTE
            parts.append(text)
            remaining -= min(len(body), limit)
        return "\n\n".join((CARRIED_HEADER, *parts)) if parts else ""
