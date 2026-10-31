"""Beceri/ajan/komut keşif kökleri ve kök imzası (P-052, P-051).

Sıra ÖNCELİKTİR: aynı adlı beceride ilk bulunan kazanır. Claude önce gelir çünkü kullanıcının
birincil kütüphanesi odur; Codex (`~/.codex/skills`, `~/.agents/skills`) ve Hermes aynı
SKILL.md biçimini kullanır. `extra_roots` (`--add-dir`, `/add-dir`) köklerinin `.claude/skills`,
`.agents/skills`, `.fusion/skills` ve `.claude/agents` dizinleri "ek-kok" etiketiyle taranır.
Yerleşik beceri/ekip EN SONDA: kullanıcı aynı adla kendi dosyasını yazarsa o kazanır.

`installed` (`fusion yetenek kur` kökü) ve `bundled` (yerleşik) yolları çağırandan gelir:
testler bu yolları `capabilities` modülü üzerinden yamalar; bu modül saf kalır.
"""

from __future__ import annotations

from pathlib import Path

#: Ek köklerin altında beceri aranan dizinler.
EXTRA_ROOT_SKILL_DIRS: tuple[Path, ...] = (
    Path(".claude") / "skills",
    Path(".agents") / "skills",
    Path(".fusion") / "skills",
)

Roots = tuple[tuple[Path, str], ...]


def skill_roots(
    home: Path, root: Path, extra_roots: tuple[Path, ...], *, installed: Path, bundled: Path
) -> Roots:
    """SKILL.md aranan kökler ve kaynak etiketleri, öncelik sırasıyla."""
    return (
        (home / ".claude" / "skills", "claude"),
        (home / ".claude" / "plugins", "claude-plugin"),
        (root / ".claude" / "skills", "proje"),
        (root / ".fusion" / "skills", "proje"),
        # Codex/ChatGPT "Agent Skills" açık standardı: ~/.agents/skills ve depo .agents/skills.
        (root / ".agents" / "skills", "proje"),
        (home / ".codex" / "skills", "codex"),
        (home / ".agents" / "skills", "codex"),
        (home / ".hermes" / "skills", "hermes"),
        *((extra / rel, "ek-kok") for extra in extra_roots for rel in EXTRA_ROOT_SKILL_DIRS),
        # `fusion yetenek kur` ile kurulan repolar (ör. stickman-video-director).
        (installed, "kurulu"),
        (bundled, "fusion"),
    )


def agent_roots(
    home: Path, root: Path, extra_roots: tuple[Path, ...], *, installed: Path, bundled: Path
) -> Roots:
    """Ajan (.md / .toml) aranan kökler, öncelik sırasıyla."""
    return (
        (home / ".claude" / "agents", "claude"),
        (root / ".claude" / "agents", "proje"),
        *((extra / ".claude" / "agents", "ek-kok") for extra in extra_roots),
        (home / ".codex" / "agents", "codex"),
        *((folder / "agents", "kurulu") for folder in installed_folders(installed)),
        (bundled, "fusion"),
    )


def installed_folders(installed: Path) -> tuple[Path, ...]:
    """`fusion yetenek kur` ile kurulan repo klasörleri."""
    if not installed.is_dir():
        return ()
    return tuple(sorted(child for child in installed.iterdir() if child.is_dir()))


def roots_signature(
    skill_roots_found: Roots, agent_roots_found: Roots, home: Path, root: Path
) -> tuple[tuple[str, int], ...]:
    """Var olan köklerin (yol, mtime_ns) imzası: klasör eklenip silinince değişir.

    Dizin mtime'ı yalnız doğrudan çocuk değişince güncellenir; bir SKILL.md'nin İÇERİĞİ
    değişince değişmez — onun için `CapabilityRegistry.invalidate()` (`/skills reload`).
    """
    from .skill_commands import COMMAND_ROOTS

    candidates = [path for path, _source in (*skill_roots_found, *agent_roots_found)]
    candidates.extend((home if in_home else root) / rel for rel, _s, in_home in COMMAND_ROOTS)
    found: list[tuple[str, int]] = []
    for path in candidates:
        try:
            found.append((str(path), path.stat().st_mtime_ns))
        except OSError:
            continue
    return tuple(found)
