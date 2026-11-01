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


#: Monorepo alt klasörlerinde tembel keşfedilen beceri dizinleri (P-052; Claude Code iç içe
#: `<alt>/.claude/skills`). Model o klasördeki bir dosyaya erişince eklenir.
NESTED_SKILL_DIRS: tuple[Path, ...] = (
    Path(".claude") / "skills",
    Path(".agents") / "skills",
)


def skill_roots(
    home: Path,
    root: Path,
    extra_roots: tuple[Path, ...],
    *,
    installed: Path,
    bundled: Path,
    nested: tuple[Path, ...] = (),
) -> Roots:
    """SKILL.md aranan kökler ve kaynak etiketleri, öncelik sırasıyla.

    `nested`: alt klasörlerde bulunmuş beceri dizinleri; proje kökündekilerden SONRA gelir
    (aynı adda kök becerisi kazanır) ve "proje" sayılır (depo içeriği, aynı güven kuralları).
    """
    return (
        (home / ".claude" / "skills", "claude"),
        (home / ".claude" / "plugins", "claude-plugin"),
        (root / ".claude" / "skills", "proje"),
        (root / ".fusion" / "skills", "proje"),
        # Codex/ChatGPT "Agent Skills" açık standardı: ~/.agents/skills ve depo .agents/skills.
        (root / ".agents" / "skills", "proje"),
        *((folder, "proje") for folder in nested),
        (home / ".codex" / "skills", "codex"),
        (home / ".agents" / "skills", "codex"),
        (home / ".hermes" / "skills", "hermes"),
        *((extra / rel, "ek-kok") for extra in extra_roots for rel in EXTRA_ROOT_SKILL_DIRS),
        # `fusion yetenek kur` ile kurulan repolar (ör. stickman-video-director).
        (installed, "kurulu"),
        (bundled, "fusion"),
    )


def agent_roots(
    home: Path,
    root: Path,
    extra_roots: tuple[Path, ...],
    *,
    installed: Path,
    bundled: Path,
    managed_roots: tuple[Path, ...] = (),
    working_directory: Path | None = None,
    extra_sources: bool = True,
) -> Roots:
    """Yönetilen kökler ve en yakın projeden başlayan ajan arama dizinleri.

    Yönetilen yolların yetkisi config çağıranındadır; burada ortam veya genel cwd okunmaz.
    CLI tanımları dosya kökü değildir; katalog onları ayrı, tiplenmiş girdilerden alır.
    `extra_sources=False`: Codex ve kurulu repo kökleri hiç taranmaz (#38).
    """
    extra: Roots = (
        (
            (home / ".codex" / "agents", "codex"),
            *((folder / "agents", "kurulu") for folder in installed_folders(installed)),
        )
        if extra_sources
        else ()
    )
    return (
        *((folder, "managed") for folder in managed_roots),
        *(
            (folder / ".claude" / "agents", "proje")
            for folder in _project_chain(root, working_directory)
        ),
        *((extra / ".claude" / "agents", "ek-kok") for extra in extra_roots),
        (home / ".claude" / "agents", "claude"),
        *extra,
        (bundled, "fusion"),
    )


def _project_chain(root: Path, working_directory: Path | None) -> tuple[Path, ...]:
    """Çalışma dizininden açık proje sınırına kadar olan kökler; dış yol taşınmaz."""
    if working_directory is None:
        return (root,)
    boundary, current = root.resolve(), working_directory.resolve()
    if not current.is_relative_to(boundary):
        return (root,)
    folders = [current]
    while current != boundary:
        current = current.parent
        folders.append(current)
    return tuple(folders)


def installed_folders(installed: Path) -> tuple[Path, ...]:
    """`fusion yetenek kur` ile kurulan repo klasörleri."""
    if not installed.is_dir():
        return ()
    return tuple(sorted(child for child in installed.iterdir() if child.is_dir()))


def roots_signature(
    skill_roots_found: Roots, agent_roots_found: Roots, home: Path, root: Path
) -> tuple[tuple[str, int], ...]:
    """Var olan köklerin (yol, mtime_ns) imzası: klasör eklenip silinince değişir.

    Dizin mtime'ı yalnız doğrudan çocuk değişince güncellenir; bu yüzden ajan dosyaları,
    kullanıcı/proje/ek kök SKILL.md dosyaları ve komut dosyaları tek tek imzaya girer.
    """
    from .skill_commands import COMMAND_ROOTS

    candidates = [path for path, _source in (*skill_roots_found, *agent_roots_found)]
    candidates.extend((home if in_home else root) / rel for rel, _s, in_home in COMMAND_ROOTS)
    # Claude Code ajan dizinlerini izler: düzenlenen dosya yeniden başlatmadan etkin olur
    # (#20). Dizin mtime'ı içerik değişince değişmediği için dosyaların kendisi de imzaya girer.
    candidates.extend(
        path
        for folder, source in agent_roots_found
        if source in _WATCHED_AGENT_SOURCES and folder.is_dir()
        for path in sorted(folder.rglob("*.md"))
    )
    # Claude Code canlı değişiklik algılama (#176): var olan becerinin/komutun düzenlenmesi
    # yeniden başlatmadan ya da `/reload-skills` olmadan etkin olur.
    candidates.extend(
        path
        for folder, source in skill_roots_found
        if source in _WATCHED_AGENT_SOURCES and folder.is_dir()
        for path in sorted(folder.rglob("SKILL.md"))
    )
    candidates.extend(
        path
        for rel, _s, in_home in COMMAND_ROOTS
        if ((home if in_home else root) / rel).is_dir()
        for path in sorted(((home if in_home else root) / rel).rglob("*.md"))
    )
    found: list[tuple[str, int]] = []
    for path in candidates:
        try:
            found.append((str(path), path.stat().st_mtime_ns))
        except OSError:
            continue
    return tuple(found)


#: İçeriği izlenen ajan kapsamları: kullanıcı, proje, yönetilen ve `--add-dir` kökleri.
_WATCHED_AGENT_SOURCES = frozenset({"claude", "proje", "managed", "ek-kok"})
