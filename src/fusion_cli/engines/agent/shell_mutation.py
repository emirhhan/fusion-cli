"""Bir kabuk komutu çalışma alanındaki dosyaları değiştirebilir mi? (WP06 kanıt tazeliği)

Tur raporu, son mutasyondan ÖNCE geçen testi kanıt saymaz. Bu yüzden iki yönlü
hata pahalıdır: değiştiren komutu kaçırmak eski başarıyı geçerli bırakır (yanlış
"doğrulandı"); zararsız komutu (mypy, derleme) mutasyon saymak geçerli kanıtı
eskitir ve ajanı testi boşuna yeniden koşturur.

Zincir (`&&`, `||`, `;`, satır sonu, boru) PARÇA PARÇA değerlendirilir: herhangi bir
parça değiştirebiliyorsa komut mutasyondur. Tanınmayan program temkinli olarak
mutasyon sayılır.
"""

from __future__ import annotations

import re
import shlex

from ...tools.auto_policy import is_read_only_command
from .verify_discovery import is_behavioral_command

_SEPARATORS = re.compile(r"&&|\|\||;|\n|\|")
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
#: `/dev/null`'a ve tanımlayıcıya (`2>&1`) yönlendirme dosya yazmaz.
_NULL_REDIRECT = re.compile(r"[\d&]?>>?\s*/dev/null|\d?>&\d")
#: Bu bayraklar denetleyiciyi düzelticiye çevirir.
_FIX_FLAGS = frozenset(
    {"--fix", "--fix-only", "--write", "-w", "--in-place", "-i", "--unsafe-fixes"}
)
#: Kaynak dosyayı değiştirmeyen statik denetim, derleme ve test araçları.
_CHECKERS = frozenset(
    {"mypy", "pyright", "tsc", "eslint", "ruff", "flake8", "pylint", "stylelint", "biome",
     "cargo", "go", "make", "gradle", "mvn", "dotnet", "swift", "xcodebuild", "pytest",
     "py_compile", "compileall", "unittest", "vitest", "jest", "playwright", "php"}
)  # fmt: skip
#: `--check`/`--diff` olmadan dosyayı yeniden yazan biçimlendiriciler.
_FORMATTERS = frozenset({"black", "isort", "prettier", "gofmt", "rustfmt"})
_JS_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_JS_SAFE_SCRIPTS = frozenset({"build", "lint", "typecheck", "test", "check", "type-check"})
_JS_WRITING = frozenset({"install", "i", "add", "ci", "remove", "uninstall", "update", "upgrade"})
_GIT_SAFE = frozenset(
    {"add", "commit", "push", "fetch", "tag", "log", "status", "diff", "show", "branch",
     "remote", "rev-parse", "ls-files", "blame", "describe", "shortlog"}
)  # fmt: skip
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree"})
#: Çıktıyı yakalayan `tee` hedefleri (günlük); kaynak dosyaya `tee` mutasyondur.
_CAPTURE_SUFFIXES = (".log", ".out")
_WRAPPERS = {"npx": 1, "bunx": 1, "pnpx": 1, "time": 1, "nohup": 1}


def shell_may_change_files(command: str) -> bool:
    """Komutun herhangi bir parçası dosya değiştirebiliyorsa True."""
    plain = _NULL_REDIRECT.sub(" ", command)
    if ">" in _QUOTED.sub(" ", plain):
        return True
    segments = [part.strip() for part in _SEPARATORS.split(plain) if part.strip()]
    return any(_segment_may_change(segment) for segment in segments)


def _segment_may_change(segment: str) -> bool:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return True  # Ayrıştırılamayan komut: emin değiliz.
    tokens = _unwrap(tokens)
    if not tokens:
        return False
    name = tokens[0].rsplit("/", 1)[-1]
    if name == "cd" or is_read_only_command(segment):
        return False
    if name == "git":
        return _git_may_change(tokens[1:])
    if name == "tee":
        return not all(
            arg.endswith(_CAPTURE_SUFFIXES) for arg in tokens[1:] if not arg.startswith("-")
        )
    if name in {"curl", "wget"}:
        return any(arg in {"-o", "-O", "--output", "--remote-name"} for arg in tokens[1:])
    if any(arg in _FIX_FLAGS for arg in tokens[1:]):
        return True
    if name in _FORMATTERS:
        return not ({"--check", "--diff", "-l", "--list-different"} & set(tokens[1:]))
    if name == "ruff" and tokens[1:2] == ["format"]:
        return "--check" not in tokens
    if name in _JS_RUNNERS:
        return _js_may_change(tokens[1:])
    # Tanınmayan program (ör. `python betik.py`) temkinli olarak mutasyondur.
    return not (name in _CHECKERS or is_behavioral_command(segment))


def _unwrap(tokens: list[str]) -> list[str]:
    """`FOO=1`, `npx`, `uv run`, `poetry run`, `python -m X` öneklerini soy."""
    while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
        tokens = tokens[1:]
    if tokens and tokens[0] in _WRAPPERS:
        return _unwrap(tokens[_WRAPPERS[tokens[0]] :])
    if tokens[:2] in (["uv", "run"], ["poetry", "run"], ["pipenv", "run"]):
        return _unwrap(tokens[2:])
    if len(tokens) >= 3 and tokens[0].rsplit("/", 1)[-1].startswith("python") and tokens[1] == "-m":
        return tokens[2:]
    return tokens


def _git_may_change(args: list[str]) -> bool:
    rest = list(args)
    while rest and rest[0].startswith("-"):
        option = rest.pop(0)
        if option in _GIT_VALUE_OPTIONS and rest:
            rest.pop(0)
    if not rest:
        return False
    sub = rest[0]
    if sub == "stash":
        return rest[1:2] not in (["list"], ["show"])
    return sub not in _GIT_SAFE


def _js_may_change(args: list[str]) -> bool:
    if not args:
        return True
    sub = args[0]
    if sub in _JS_WRITING:
        return True
    if sub in {"test", "t"}:
        return False
    if sub == "run" and len(args) > 1:
        return args[1] not in _JS_SAFE_SCRIPTS
    return sub not in _JS_SAFE_SCRIPTS
