"""`/doctor prompt-audit [yol]`: talimat dosyalarının model denetimi (Claude Code #168).

Claude Code (code.claude.com/docs/en/memory, "Audit your instruction files"; commands
`/doctor`): `/doctor prompt-audit [path]` CLAUDE.md, AGENTS.md, kurallar, beceriler, komutlar,
alt ajanlar ve çıktı stillerini modelle denetler — eskimiş talimat, var olmayan dosya ya da
komuta gönderme, birbiriyle çelişen kurallar — ve düzenleme önerir; onay olmadan dosya
değiştirmez. `/doctor` bir paket becerisidir: işi model yapar.

Fusion'da görev, kapsamdaki dosyaların listesi ve kural tabanlı ön bulgularla kurulur; tur
`/init` gibi sıradaki agent turunda koşar. Yol verilirse yalnız o dosya ya da o dizinin
altındaki talimat dosyaları denetlenir.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Görevde tek tek listelenen en çok dosya (gerisi sayıyla belirtilir).
MAX_LISTED_FILES = 120

#: Kökten (proje ya da `~`) göreli talimat dosyası kalıpları.
_ROOT_FILES = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md", "AGENTS.md")
_GLOBS = (
    ".claude/rules/**/*.md",
    ".claude/skills/*/SKILL.md",
    ".claude/commands/**/*.md",
    ".claude/agents/**/*.md",
    ".claude/output-styles/**/*.md",
)
#: İç içe CLAUDE.md/AGENTS.md ararken atlanan büyük dizinler.
_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "dist", "build", "target"})


def _under(base: Path) -> list[Path]:
    found = [base / name for name in _ROOT_FILES if (base / name).is_file()]
    for pattern in _GLOBS:
        found.extend(sorted(path for path in base.glob(pattern) if path.is_file()))
    return found


def _nested(base: Path) -> list[Path]:
    """Alt dizinlerdeki CLAUDE.md / AGENTS.md (büyük üretim dizinlerine inilmez)."""
    found: list[Path] = []
    for folder, dirs, names in os.walk(base):
        dirs[:] = sorted(name for name in dirs if name not in _SKIP_DIRS)
        if Path(folder) == base:
            continue
        found.extend(Path(folder) / name for name in ("CLAUDE.md", "AGENTS.md") if name in names)
    return found


def audit_scope(root: Path, home: Path | None, target: str = "") -> tuple[Path, ...]:
    """Denetlenecek dosyalar: yol yoksa kullanıcı + proje katmanları, varsa yalnız o yol."""
    if target.strip():
        chosen = Path(target.strip()).expanduser()
        chosen = chosen if chosen.is_absolute() else root / chosen
        if chosen.is_file():
            return (chosen,)
        if not chosen.is_dir():
            return ()
        files = [*_under(chosen), *_nested(chosen)]
        if ".claude" in chosen.resolve().parts:
            # `.claude/rules`, `.claude/skills/x` gibi bir talimat dizini: içindeki tüm .md.
            files.extend(sorted(path for path in chosen.rglob("*.md") if path.is_file()))
    else:
        files = [*(_under(home) if home is not None else []), *_under(root), *_nested(root)]
    return tuple(dict.fromkeys(path.resolve() for path in files))


def _display(path: Path, root: Path, home: Path | None) -> str:
    for base, prefix in ((root, ""), (home, "~/")):
        if base is None:
            continue
        try:
            return prefix + path.relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return str(path)


def prompt_audit_task(
    root: Path, home: Path | None, target: str = "", *, findings: str = ""
) -> str:
    """Modele verilecek denetim görevi; kapsam boşsa boş metin."""
    files = audit_scope(root, home, target)
    if not files:
        return ""
    listed = [f"- `{_display(path, root, home)}`" for path in files[:MAX_LISTED_FILES]]
    if len(files) > MAX_LISTED_FILES:
        listed.append(f"- … ve {len(files) - MAX_LISTED_FILES} dosya daha")
    parts = [
        "Talimat dosyalarını denetle (Claude Code `/doctor prompt-audit`). Kapsamdaki her "
        "dosyayı oku ve şunları ara: eskimiş ya da artık doğru olmayan talimatlar; var olmayan "
        "dosya, dizin, betik ya da komuta göndermeler (depoda doğrula); birbiriyle ya da başka "
        "dosyayla çelişen kurallar; yinelenen, belirsiz ya da gereğinden uzun talimatlar; "
        "beceri/komut/alt ajan frontmatter'ında eksik ya da yanlış alanlar.",
        "Kapsam:\n" + "\n".join(listed),
    ]
    if findings:
        parts.append("Fusion'ın kural tabanlı ön bulguları (doğrula, yinele değil):\n" + findings)
    parts.append(
        "Sonuçta her bulgu için dosya ve satır, sorun ve önerilen düzenlemeyi ver. Dosyaları "
        "DEĞİŞTİRME: önce önerileri listele, kullanıcı onaylarsa ancak o zaman uygula."
    )
    return "\n\n".join(parts)
