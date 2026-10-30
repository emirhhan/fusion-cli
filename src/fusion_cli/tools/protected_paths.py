"""Korumalı proje yolları (P-002): `.git/`, `.claude/`, `.fusion/tools/` ve benzerleri.

Claude Code bu yollara yazmayı her kipte onaya bağlar: sürüm geçmişi, izin listesi,
ajan/skill tanımları ve Fusion'ın ürettiği araçlar değiştirilirse ajan kendi sınırlarını
genişletebilir ("`.claude/settings.local.json`'a `Bash(*)` yaz" → onaysız komut).
Bu yüzden korumalı yola yazan `write_file`/`edit_file`/kabuk komutu YIKICI sayılır:
Otomatik ve Düzenlemeleri kabul et kiplerinde de sorulur, oturum iznine dönüşmez.

Okuma serbesttir (`git log`, `.claude/agents` okumak işin parçasıdır); yalnız YAZAN
ve SİLEN çağrı yakalanır. Ölçüldü (31 Ekim): `write_file .claude/settings.local.json`
auto kipte sorulmuyordu, `rm -rf .git` sade `rm` sayılıp çöpe gidiyordu.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .auto_policy import command_words, is_read_only_command, written_files

#: Köke göreli korumalı yol ön ekleri (posix). Sıra önemsizdir.
PROTECTED_PATHS: tuple[str, ...] = (
    ".git",
    ".claude",
    ".fusion/tools",
    ".codex",
    ".cursor/rules",
    ".github/workflows",
)
#: Hedef yolu `path` argümanında taşıyan yerel yazma araçları.
_PATH_WRITE_TOOLS = frozenset({"write_file", "edit_file", "multi_edit", "create_file"})
#: Argümanları arasında dosya yolu geçen ve o yolu DEĞİŞTİREBİLEN kabuk komutları.
_MUTATING_COMMANDS = frozenset(
    {"rm", "mv", "cp", "ln", "touch", "mkdir", "rmdir", "chmod", "chown", "sed", "tee",
     "truncate", "install", "rsync", "unlink", "shred", "rimraf", "git", "echo", "cat", "printf"}
)  # fmt: skip
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
    if tool_name not in _PATH_WRITE_TOOLS:
        return None
    raw = args.get("path")
    hit = _protected_hit(raw, root) if isinstance(raw, str) else None
    return PROTECTED_REASON.format(yol=hit) if hit else None


def _shell_reason(command: str, root: Path) -> str | None:
    if is_read_only_command(command):
        return None
    candidates = list(written_files(command))
    for parts in command_words(command):
        name = parts[0].rsplit("/", 1)[-1]
        if name in _MUTATING_COMMANDS:
            candidates.extend(token for token in parts[1:] if not token.startswith("-"))
    for token in candidates:
        hit = _protected_hit(token, root)
        if hit:
            return PROTECTED_REASON.format(yol=hit)
    return None


def _protected_hit(raw: str, root: Path) -> str | None:
    """Yol korumalı ön eklerden birinin altındaysa o ön eki döndür."""
    text = raw.strip().strip("'\"")
    if not text or text.startswith(("-", "$")):
        return None
    try:
        path = Path(text).expanduser()
        absolute = path if path.is_absolute() else root / path
        relative = os.path.relpath(os.path.normpath(absolute), os.path.normpath(root))
    except (OSError, RuntimeError, ValueError):
        return None
    posix = PurePosixPath(relative).as_posix()
    if posix.startswith(".."):
        return None
    for prefix in PROTECTED_PATHS:
        if posix == prefix or posix.startswith(prefix + "/"):
            return prefix
    return None
