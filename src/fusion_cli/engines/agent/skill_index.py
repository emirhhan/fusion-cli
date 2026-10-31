"""Beceri dizini: skill adlarının ve kısa açıklamalarının sistem bağlamına bütçeli enjeksiyonu.

Claude Code her istekte tüm skill'lerin `name + description` çiftini sistem istemine koyar
(progressive disclosure: gövde yalnız kullanımda yüklenir) ve model uygun beceriyi aramadan
kendisi tetikler. Fusion'da liste modele hiç basılmıyordu; model `find_skill` ile aramak
zorundaydı ve ölçüm (expertise.py) bunu neredeyse hiç yapmadığını gösterdi (1.696 araç
çağrısında 0 find_skill).

Bu modül dizini üretir: beceri başına tek satır (`ad — açıklama[:150]`), toplam bütçe
`runtime.skill_index_chars` (varsayılan 4.000; küçük pencereli modelde pencerenin %2'si).
Sıra keşif sırasıdır (kaynak önceliği: kullanıcı kökleri → proje → dış araçlar → yerleşik).
Bütçe aşılırsa kalan sayı ve "find_skill ile ara" notu düşer. `disable-model-invocation`
olan beceriler dizine girmez (yalnız kullanıcı `/ad` ile çağırır).

Sıkıştırma: dizin sistem bağlamındadır ve her turda yeniden kurulur; `compaction` yalnız
konuşma mesajlarını özetlediği için dizin kaybolmaz (ayrı bir koruma gerekmez).

Güven: depo kaynaklı beceriler (`proje`, `ek-kok`, `kurulu`, `claude-plugin`) ayrı bir
`<proje_becerileri>` bloğunda, `UNTRUSTED_NOTE` ile ve etiket kapatmaları nötralize edilerek
listelenir — açıklama alanı klonlanan deponun metnidir, kullanıcı sözü değildir (ölçüldü
31 Ekim: etiketsiz basılıyordu).
"""

from __future__ import annotations

from ...config.models import Config
from ...tools.capabilities import Capability, CapabilityRegistry
from .context_budget import CHARS_PER_TOKEN_ESTIMATE, context_budget
from .instruction_layers import UNTRUSTED_NOTE, neutralize

#: Depo içeriği sayılan kaynaklar; yalnız bunlardan gelen beceri güvenilmez bloğa girer.
REPO_SOURCES = frozenset({"proje", "ek-kok", "kurulu", "claude-plugin"})

REPO_OPEN = "<proje_becerileri>"
REPO_CLOSE = "</proje_becerileri>"

#: Varsayılan dizin bütçesi (karakter); `runtime.skill_index_chars` ile değişir.
SKILL_INDEX_CHARS = 4_000

#: Küçük pencereli modelde dizin pencerenin bu payını aşmaz (harita %3, dizin %2).
INDEX_WINDOW_SHARE = 0.02

#: Pencere çok dar olsa da en az bu kadar yer ayrılır (birkaç beceri sığsın).
INDEX_MIN_CHARS = 600

#: Satır başına açıklamanın en fazla uzunluğu.
DESCRIPTION_CHARS = 150

HEADER = (
    "BECERİ DİZİNİ (ad — ne işe yarar). Görev bunlardan birine uyuyorsa ÖNCE "
    "read_skill('<ad>') ile talimatı yükle, sonra uygula; listede yoksa find_skill ile ara."
)


def index_budget_for(config: Config) -> int:
    """Turun etkin dizin bütçesi: `runtime.skill_index_chars` ve modelin penceresi."""
    runtime = getattr(config, "runtime", None)
    configured = int(getattr(runtime, "skill_index_chars", SKILL_INDEX_CHARS))
    if configured <= 0:
        return 0
    try:
        window = context_budget(config, config.agent).window_tokens
    except (AttributeError, TypeError, ValueError):
        return configured
    if not window:
        return configured
    cap = int(window * CHARS_PER_TOKEN_ESTIMATE * INDEX_WINDOW_SHARE)
    return min(configured, max(INDEX_MIN_CHARS, cap))


def _line(name: str, description: str) -> str:
    summary = " ".join(description.split())
    if len(summary) > DESCRIPTION_CHARS:
        summary = summary[: DESCRIPTION_CHARS - 1].rstrip() + "…"
    return f"- {name} — {summary}" if summary else f"- {name}"


def is_repo_sourced(skill: Capability) -> bool:
    """Beceri yalnız depo kaynaklarından mı geliyor (kullanıcı kökünde kopyası yok)?"""
    return set(skill.source.split("+")) <= REPO_SOURCES


def skill_index_block(registry: CapabilityRegistry | None, budget: int = SKILL_INDEX_CHARS) -> str:
    """Dizin bloğu; kütüphane boşsa ya da bütçe 0 ise boş dize.

    Kullanıcı kökündeki beceriler önce ve düz; depo kaynaklılar `<proje_becerileri>` içinde.
    """
    if registry is None or budget <= 0:
        return ""
    skills = [item for item in registry.skills() if item.model_invocable]
    if not skills:
        return ""
    trusted = [item for item in skills if not is_repo_sourced(item)]
    repo = [item for item in skills if is_repo_sourced(item)]
    wrapper_cost = sum(len(part) + 1 for part in (REPO_OPEN, UNTRUSTED_NOTE, REPO_CLOSE))
    lines: list[str] = [HEADER]
    remaining = budget - len(HEADER) - (wrapper_cost if repo else 0)
    shown = 0
    for skill in trusted:
        line = _line(skill.name, skill.description)
        if len(line) + 1 > remaining:
            break
        lines.append(line)
        remaining -= len(line) + 1
        shown += 1
    repo_lines: list[str] = []
    for skill in repo:
        line = neutralize(_line(skill.name, skill.description))
        if len(line) + 1 > remaining:
            break
        repo_lines.append(line)
        remaining -= len(line) + 1
        shown += 1
    if repo_lines:
        lines.extend([REPO_OPEN, UNTRUSTED_NOTE, *repo_lines, REPO_CLOSE])
    hidden = len(skills) - shown
    if hidden:
        lines.append(f"[…+{hidden} beceri daha listeye sığmadı; find_skill ile ara.]")
    if shown == 0 and hidden:
        # Hiçbir satır sığmadı: en azından aramayı öner (başlık + not).
        return "\n".join([HEADER, lines[-1]])
    return "\n".join(lines)
