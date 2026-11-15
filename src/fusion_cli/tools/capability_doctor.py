"""Beceri/ajan kataloğu teşhisi — `/skills doctor`, `/skill-doctor`, `yetenek.teshis` (P-051).

Claude Code'un `/skill-doctor` komutu gibi: eksik `name`/`description`, ön maddesiz dosya,
aynı adın birden çok kaynakta bulunması (kazanan ve gölgelenen), tek sayfaya sığmayacak
gövde ve kök dışına çıkan sembolik bağ. Bulgu engellemez; kullanıcıya ne düzelteceğini söyler.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capabilities import Capability, CapabilityRegistry
from .frontmatter import parse_frontmatter
from .skill_pages import SKILL_TEXT_BUDGET


@dataclass(frozen=True, slots=True)
class CapabilityIssue:
    """Tek bir teşhis bulgusu."""

    #: eksik_aciklama | frontmatter_yok | kopya_ad | uzun_govde | kok_disi_bag | okunamadi
    kind: str
    name: str
    #: "uyari" (davranışı etkiler) | "bilgi" (kozmetik ya da bilinçli olabilir)
    severity: str
    detail: str
    path: str = ""

    def render(self) -> str:
        isaret = "!" if self.severity == "uyari" else "·"
        return f"{isaret} {self.name}: {self.detail}" + (f"  ({self.path})" if self.path else "")


def diagnose(registry: CapabilityRegistry) -> tuple[CapabilityIssue, ...]:
    """Katalogdaki beceri ve ajanları denetle; temiz katalogda boş demet."""
    issues: list[CapabilityIssue] = []
    skills = registry.skills()
    for item in skills:
        issues.extend(_inspect(item, budget=SKILL_TEXT_BUDGET))
    for item in registry.agents():
        issues.extend(_inspect(item, budget=None))
    issues.extend(_duplicates(skills))
    return tuple(issues)


def _inspect(item: Capability, *, budget: int | None) -> list[CapabilityIssue]:
    found: list[CapabilityIssue] = []
    try:
        text = item.path.read_text(encoding="utf-8")
    except OSError as error:
        return [
            CapabilityIssue("okunamadi", item.name, "uyari", f"okunamadı: {error}", str(item.path))
        ]
    if item.kind != "komut" and item.path.suffix.lower() != ".toml":
        fields = parse_frontmatter(text)
        if not fields:
            found.append(
                CapabilityIssue(
                    "frontmatter_yok",
                    item.name,
                    "uyari",
                    "ön madde (--- name/description ---) yok; ad klasör adından türetildi",
                    str(item.path),
                )
            )
    if not item.description.strip():
        found.append(
            CapabilityIssue(
                "eksik_aciklama",
                item.name,
                "uyari",
                "description boş: beceri dizininde ve aramada tanınmaz",
                str(item.path),
            )
        )
    if budget is not None and len(text) > budget:
        found.append(
            CapabilityIssue(
                "uzun_govde",
                item.name,
                "bilgi",
                f"gövde {len(text)} karakter; tek sayfada {budget} okunur, devamı "
                "read_skill(offset)",
                str(item.path),
            )
        )
    if item.path.is_symlink():
        found.extend(_symlink_issue(item))
    return found


def _symlink_issue(item: Capability) -> list[CapabilityIssue]:
    try:
        target = item.path.resolve()
    except OSError:
        return []
    home = Path.home().resolve()
    if target.is_relative_to(home):
        return []
    return [
        CapabilityIssue(
            "kok_disi_bag",
            item.name,
            "bilgi",
            f"sembolik bağ ev dizini dışına çıkıyor: {target}",
            str(item.path),
        )
    ]


def _duplicates(skills: tuple[Capability, ...]) -> list[CapabilityIssue]:
    """Aynı ad birden çok kaynakta farklı içerikle: ilk bulunan (öncelikli kök) kazanır."""
    by_name: dict[str, list[Capability]] = {}
    for item in skills:
        by_name.setdefault(item.name, []).append(item)
    found: list[CapabilityIssue] = []
    for name, items in by_name.items():
        if len(items) < 2:
            continue
        winner, *shadowed = items
        found.append(
            CapabilityIssue(
                "kopya_ad",
                name,
                "uyari",
                f"{len(items)} kaynakta farklı içerik; kazanan: {winner.source}, gölgelenen: "
                + ", ".join(s.source for s in shadowed)
                + " — nitelikli adla çağır (read_skill('ad@kaynak:…'))",
                str(winner.path),
            )
        )
    return found


def render_report(issues: tuple[CapabilityIssue, ...], *, skills: int, agents: int) -> str:
    """Terminal/masaüstü için okunur özet."""
    baslik = f"Beceri teşhisi: {skills} beceri, {agents} ajan tarandı."
    if not issues:
        return f"{baslik} Sorun bulunmadı."
    uyari = sum(1 for i in issues if i.severity == "uyari")
    satirlar = [f"{baslik} {uyari} uyarı, {len(issues) - uyari} bilgi:"]
    satirlar.extend(issue.render() for issue in issues)
    return "\n".join(satirlar)
