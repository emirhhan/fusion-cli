"""Korumalı proje yolları (P-002): `.git/`, `.claude/`, `.fusion/tools/` ve benzerleri.

Claude Code bu yollara yazmayı her kipte onaya bağlar: sürüm geçmişi, izin listesi,
ajan/skill tanımları ve Fusion'ın ürettiği araçlar değiştirilirse ajan kendi sınırlarını
genişletebilir ("`.claude/settings.local.json`'a `Bash(*)` yaz" → onaysız komut).
Bu yüzden korumalı yola yazan `write_file`/`edit_file`/kabuk komutu YIKICI sayılır:
Otomatik ve Düzenlemeleri kabul et kiplerinde de sorulur, oturum iznine dönüşmez.

Okuma serbesttir (`git log`, `.claude/agents` okumak işin parçasıdır); yalnız YAZAN
ve SİLEN çağrı yakalanır. Ölçüldü (31 Ekim): `write_file .claude/settings.local.json`
auto kipte sorulmuyordu, `rm -rf .git` sade `rm` sayılıp çöpe gidiyordu.

Kapsam (ölçüldü, 31 Ekim, ikinci tur): yazan araç listesi `write_targets` ile ortaktır
(`download_file`, `extract_archive`, görsel araçları dahil); kabukta `cd X && …` sonrası
göreli hedefler `X`e göre çözülür, `-C` alan arşiv/git komutları ve `curl -o`/`wget -O`
yazıcı sayılır; karşılaştırma büyük/küçük harf duyarsızdır (`.GIT/config`, macOS).

Bilinen sınır: `python -c "open('.git/x','w')"` gibi satır içi kod statik olarak
çözülemez; o yol `auto_policy.inline_code_danger` ile ayrı denetlenir.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .auto_policy import command_words, is_read_only_command, written_files
from .write_targets import write_targets

#: Korumalı dizinler (Claude Code listesi, #69). Yolun HERHANGİ bir bölümü bu adsa korunur.
PROTECTED_DIRS: tuple[str, ...] = (
    ".git",
    ".config/git",
    ".vscode",
    ".idea",
    ".husky",
    ".cargo",
    ".devcontainer",
    ".yarn",
    ".mvn",
    ".claude",
    # Fusion eki: Fusion'ın kendi yapılandırma kökleri (Claude'un `.claude`u korumasıyla aynı
    # ilke; buralardan ajan/beceri/araç tanımı okunur, bkz. `capability_roots`).
    ".fusion",
    ".codex",
    ".cursor/rules",
)
#: Korumalı dosyalar (Claude Code listesi): ad her dizinde eşleşir.
PROTECTED_FILES = frozenset(
    {".gitconfig", ".gitmodules", ".bashrc", ".bash_profile", ".bash_login", ".bash_aliases",
     ".bash_logout", ".zshrc", ".zprofile", ".zshenv", ".zlogin", ".zlogout", ".profile",
     ".envrc", ".npmrc", ".yarnrc", ".yarnrc.yml", ".pnp.cjs", ".pnp.loader.mjs",
     ".pnpmfile.cjs", "bunfig.toml", ".bunfig.toml", ".bazelrc", ".bazelversion",
     ".bazeliskrc", ".pre-commit-config.yaml", "lefthook.yml", "lefthook.yaml",
     ".lefthook.yml", ".lefthook.yaml", "gradle-wrapper.properties",
     "maven-wrapper.properties", ".devcontainer.json", ".ripgreprc", "pyrightconfig.json",
     ".mcp.json", ".claude.json"}
)  # fmt: skip
#: Geriye uyum: eski ad.
PROTECTED_PATHS = PROTECTED_DIRS
#: `.claude` istisnaları (Claude): kendi worktree'leri, planlar, iş geçici dizini, bellek .md'leri.
_CLAUDE_EXCEPTIONS = re.compile(
    r"(?:^|/)\.claude/worktrees(?:/|$)"
    r"|(?:^|/)\.claude/plans(?:/|$)"
    r"|(?:^|/)\.claude/jobs/[^/]+/tmp(?:/|$)"
    r"|(?:^|/)\.claude/agent-memory(?:-local)?/.*\.md$"
    r"|(?:^|/)\.claude/projects/[^/]+/memory/.*\.md$"
)
#: Argümanları arasında dosya yolu geçen ve o yolu DEĞİŞTİREBİLEN kabuk komutları.
_MUTATING_COMMANDS = frozenset(
    {"rm", "mv", "cp", "ln", "touch", "mkdir", "rmdir", "chmod", "chown", "sed", "tee",
     "truncate", "install", "rsync", "unlink", "shred", "rimraf", "git", "echo", "cat", "printf",
     "tar", "unzip", "zip", "gzip", "gunzip", "bsdtar", "patch", "dd", "curl", "wget", "ditto"}
)  # fmt: skip
#: Çalışma dizinini değiştiren komut: sonraki parçaların göreli hedefleri ona göre çözülür.
_CD = "cd"
#: Kabuk komutu bu yola yazıyor/siliyor ise kullanıcıya gösterilen gerekçe.
PROTECTED_REASON = "korumalı proje yoluna yazma ({yol})"


def protected_path_reason(
    tool_name: str, args: Mapping[str, object], root: Path | None, *, is_shell: bool = False
) -> str | None:
    """Çağrı korumalı bir yolu değiştiriyorsa gerekçe; değilse None."""
    if root is None:
        return None
    if is_shell:
        command = args.get("command")
        return _shell_reason(command, root) if isinstance(command, str) else None
    for raw in write_targets(tool_name, args):
        hit = _protected_hit(raw, root)
        if hit:
            return PROTECTED_REASON.format(yol=hit)
    return None


def _shell_reason(command: str, root: Path) -> str | None:
    if is_read_only_command(command):
        return None
    # `cd X && komut`: göreli hedefler X'e göre de çözülür. Hangi yönlendirmenin hangi
    # `cd`den sonra geldiği bilinmediğinden hedefler görülen HER dizine göre denenir —
    # fazladan soru güvenli taraftır.
    bases: list[Path] = [root]
    candidates = list(written_files(command))
    for parts in command_words(command):
        name = parts[0].rsplit("/", 1)[-1]
        if name == _CD:
            target = next((token for token in parts[1:] if not token.startswith("-")), None)
            if target is not None:
                bases.append(_resolve(target, bases[-1]))
                candidates.append(target)
            continue
        if name in _MUTATING_COMMANDS:
            candidates.extend(token for token in parts[1:] if not token.startswith("-"))
    for token in candidates:
        for base in bases:
            hit = _protected_hit(token, root, base)
            if hit:
                return PROTECTED_REASON.format(yol=hit)
    return None


def _resolve(raw: str, base: Path) -> Path:
    text = raw.strip().strip("'\"")
    path = Path(text).expanduser()
    return path if path.is_absolute() else base / path


def _protected_hit(raw: str, root: Path, base: Path | None = None) -> str | None:
    """Yol korumalı ön eklerden birinin altındaysa o ön eki döndür (`base`: göreli yolun kökü)."""
    text = raw.strip().strip("'\"")
    if not text or text.startswith(("-", "$")):
        return None
    try:
        absolute = _resolve(text, base or root)
        relative = os.path.relpath(os.path.normpath(absolute), os.path.normpath(root))
    except (OSError, RuntimeError, ValueError):
        return None
    inside = not relative.startswith("..")
    posix = PurePosixPath(relative if inside else os.path.normpath(absolute)).as_posix().lower()
    return protected_hit(posix)


def protected_hit(posix: str) -> str | None:
    """Küçük harfli posix yol korumalı dizin/dosyaya düşüyorsa korunan öğe (#69)."""
    if _CLAUDE_EXCEPTIONS.search(posix):
        return None
    padded = f"/{posix.strip('/')}/"
    for prefix in PROTECTED_DIRS:
        if f"/{prefix}/" in padded:
            return prefix
    name = posix.rstrip("/").rsplit("/", 1)[-1]
    return name if name in PROTECTED_FILES else None
