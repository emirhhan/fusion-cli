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
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .auto_policy import command_words, is_read_only_command, written_files
from .write_targets import write_targets

#: Köke göreli korumalı yol ön ekleri (posix). Sıra önemsizdir.
PROTECTED_PATHS: tuple[str, ...] = (
    ".git",
    ".claude",
    ".fusion/tools",
    ".codex",
    ".cursor/rules",
    ".github/workflows",
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
    posix = PurePosixPath(relative).as_posix().lower()
    if posix.startswith(".."):
        return None
    for prefix in PROTECTED_PATHS:
        if posix == prefix or posix.startswith(prefix + "/"):
            return prefix
    return None
