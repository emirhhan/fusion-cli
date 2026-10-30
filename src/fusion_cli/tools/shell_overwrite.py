"""Kabuk komutunun ezeceği proje dosyalarını bul (T1-18).

Ölçüldü (30 Ekim): `command_policy` proje içi `cp`/`mv`/`>` komutlarını sormadan
geçirir (26 Eylül kararı: `write_file` da sormuyor). Ama `write_file` ezmeden önce
`changes.record` ile anlık görüntü alır, kabuk yolu almazdı: `cp a b` ya da
`echo x > notlar.txt` var olan dosyanın içeriğini geri alınamaz biçimde yitirirdi
(`rm` çöpe gider, bunlar gitmezdi).

Bu modül komut ÇALIŞMADAN önce ezilecek / taşınacak mevcut proje dosyalarını bulur;
`run_shell` bunları `context.changes.record` ile kaydeder. Soru sormaz: kullanıcıyı
yormadan aynı güvenceyi `write_file` ile eşitler. Tam kabuk ayrıştırması imkânsızdır;
tanınmayan biçim (değişken, alt kabuk) kayıt almaz, davranışı eskisi gibi bırakır.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from ..core.constants import SHELL_BACKUP_MAX_BYTES

_SEPARATORS = frozenset({";", "&&", "||", "|", "&", "|&"})
_COPY_MOVE = frozenset({"cp", "mv"})
_TARGET_DIR_FLAGS = frozenset({"-t", "--target-directory"})
_GLOB_CHARS = "*?["
_UNKNOWN_PATH_CHARS = "$`~"


def backup_paths(command: str, root: Path) -> list[Path]:
    """Komutun ezeceği/taşıyacağı, projede MEVCUT dosyalar (yinelenmeden, sıralı)."""
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return []
    found: list[Path] = []
    for segment in _segments(tokens):
        for path in _segment_paths(segment, root):
            if path not in found:
                found.append(path)
    return found


def _segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _is_redirect(token: str) -> bool:
    return ">" in token and all(char in "&>|" for char in token)


def _segment_paths(segment: list[str], root: Path) -> list[Path]:
    words: list[str] = []
    redirect_targets: list[str] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        if _is_redirect(token):
            target = segment[index + 1] if index + 1 < len(segment) else ""
            # `2>&1`: hedef bir dosya tanımlayıcısıdır, dosya değil.
            if not (token.endswith("&") and (target.isdigit() or target == "-")):
                redirect_targets.append(target)
            index += 2
            continue
        words.append(token)
        index += 1
    candidates = [_resolve(target, root) for target in redirect_targets]
    candidates += _command_paths(words, root)
    return [path for path in candidates if path is not None and _is_backable(path, root)]


def _command_paths(words: list[str], root: Path) -> list[Path | None]:
    if not words:
        return []
    name = words[0].rsplit("/", 1)[-1]
    if name == "tee":
        return [_resolve(word, root) for word in words[1:] if not word.startswith("-")]
    if name not in _COPY_MOVE:
        return []
    return _copy_move_paths(name, words[1:], root)


def _copy_move_paths(name: str, arguments: list[str], root: Path) -> list[Path | None]:
    positional: list[str] = []
    target_dir: str | None = None
    skip_next = False
    for position, argument in enumerate(arguments):
        if skip_next:
            skip_next = False
        elif argument in _TARGET_DIR_FLAGS and position + 1 < len(arguments):
            target_dir = arguments[position + 1]
            skip_next = True
        elif argument.startswith("--target-directory="):
            target_dir = argument.split("=", 1)[1]
        elif not (argument.startswith("-") and len(argument) > 1):
            positional.append(argument)
    if target_dir is None:
        if len(positional) < 2:
            return []
        target_dir, sources = positional[-1], positional[:-1]
    else:
        sources = positional
    destination = _resolve(target_dir, root)
    if destination is None:
        return []
    source_paths = [path for source in sources for path in _expand(source, root)]
    paths: list[Path | None] = []
    for source in source_paths:
        if name == "mv":
            paths.append(source)
        paths.append(destination / source.name if destination.is_dir() else destination)
    return paths


def _expand(word: str, root: Path) -> list[Path]:
    if any(char in word for char in _GLOB_CHARS) and not word.startswith("/"):
        return sorted(root.glob(word))
    resolved = _resolve(word, root)
    return [] if resolved is None else [resolved]


def _resolve(word: str, root: Path) -> Path | None:
    if not word or any(char in word for char in _UNKNOWN_PATH_CHARS + _GLOB_CHARS):
        return None
    if word == "/dev/null":
        return None
    path = Path(word)
    return path if path.is_absolute() else root / path


def _is_backable(path: Path, root: Path) -> bool:
    """Proje İÇİNDE, mevcut, düz dosya ve bellekte tutulacak kadar küçük mü?"""
    try:
        resolved_root = root.resolve()
        resolved = path.resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            return False
        return path.is_file() and path.stat().st_size <= SHELL_BACKUP_MAX_BYTES
    except OSError:
        return False
