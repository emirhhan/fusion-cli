"""Plan kipinde sınıflandırıcının kabuk komutu kararı (#318).

Claude Code plan kipinde salt okunur olmayan komutu otomatik kip sınıflandırıcısına verir;
o sınıflandırıcı plan kipini bilen bir modeldir ve plan "kaynağı düzenlemez" (permission-modes).
Fusion'ın otomatik kip denetçisi ise kipten habersiz bir sezgidir (`auto_risk`), bu yüzden
burada KAPALI LİSTE değil AÇIK LİSTE uygulanır (bağımsız inceleme, 1 Kasım):

- salt okunur komut ya da bilinen kurulum/derleme/test komutu → sormadan çalışır (`ALLOW`);
- dosya yazan/silen/taşıyan ya da git çalışma ağacını değiştiren komut → engellenir (`BLOCK`);
- geri kalan her şey (yorumlayıcıda satır içi kod, alt kabuk, bilinmeyen araç) → sorulur
  (`ASK`): Claude'un sınıflandırıcı yokken yaptığı gibi.
"""

from __future__ import annotations

import re
from enum import Enum

from ...tools.auto_policy import command_words, reads_only_words, written_files


class PlanVerdict(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ASK = "ask"


#: Doğrudan dosya sistemi düzenleyen komutlar (plan kipinde sınıflandırıcı reddeder).
_EDITING_COMMANDS = frozenset(
    {
        "rm", "rmdir", "mv", "cp", "touch", "mkdir", "ln", "chmod", "chown", "truncate",
        "dd", "install", "rsync", "patch", "unzip", "tar", "trash", "shred", "wget",
    }
)  # fmt: skip
#: Çalışma ağacını değiştiren git alt komutları.
_EDITING_GIT = frozenset(
    {"add", "commit", "checkout", "switch", "reset", "restore", "merge", "rebase", "stash",
     "apply", "am", "cherry-pick", "revert", "rm", "mv", "clean", "pull", "push", "tag"}
)  # fmt: skip
#: git'in alt komuttan önce gelen, değer alan genel seçenekleri (`git -C dizin reset`).
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_CURL_OUTPUT = frozenset({"-o", "-O", "--output", "--remote-name", "--remote-name-all"})
_FIND_EDITING = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint"})
#: Kaynağı düzenlemeyen bilinen kurulum/derleme/test komutları: ad → izinli alt komutlar
#: (`None`: her argüman). Düzeltme bayrakları (`--fix`, `--write`) her zaman dışarıda.
_BUILD_COMMANDS: dict[str, frozenset[str] | None] = {
    "pytest": None,
    "py.test": None,
    "mypy": None,
    "jest": None,
    "vitest": None,
    "npm": frozenset({"install", "i", "ci", "test", "t", "run"}),
    "pnpm": frozenset({"install", "i", "test", "t", "run"}),
    "yarn": frozenset({"install", "test", "run", "build"}),
    "bun": frozenset({"install", "test", "run"}),
    "cargo": frozenset({"build", "test", "check", "clippy", "bench", "doc"}),
    "go": frozenset({"build", "test", "vet"}),
    "make": frozenset({"test", "check", "build", "all"}),
    "ruff": frozenset({"check"}),
    "pip": frozenset({"install"}),
    "pip3": frozenset({"install"}),
}
_RUN_SCRIPTS = frozenset({"test", "build", "typecheck", "type-check", "check"})
_PYTHON_MODULES = frozenset({"pytest", "mypy", "unittest", "pip"})
_FIX_FLAGS = re.compile(r"^--(fix|write|in-place|update-snapshots?)\b|^-u$")


def plan_verdict(command: str) -> PlanVerdict:
    """Plan kipinde sınıflandırıcı bu komuta ne der?"""
    if edits_source(command):
        return PlanVerdict.BLOCK
    if "$(" in command or "`" in command:
        return PlanVerdict.ASK
    segments = command_words(command)
    if segments and all(_plan_safe(parts) for parts in segments):
        return PlanVerdict.ALLOW
    return PlanVerdict.ASK


def edits_source(command: str, depth: int = 0) -> bool:
    """Komut dosya yazıyor, siliyor, taşıyor ya da git çalışma ağacını değiştiriyor mu?"""
    if any(target != "/dev/null" for target in written_files(command)):
        return True
    return any(_segment_edits(parts, depth) for parts in command_words(command))


def _segment_edits(parts: list[str], depth: int) -> bool:
    name, arguments = parts[0].rsplit("/", 1)[-1], parts[1:]
    if name in _EDITING_COMMANDS:
        return True
    if name == "git":
        return _git_subcommand(arguments) in _EDITING_GIT
    if name in _SHELLS:
        nested = _shell_script(arguments)
        return nested is not None and depth < 3 and edits_source(nested, depth + 1)
    return _edit_flag(name, arguments)


def _edit_flag(name: str, arguments: list[str]) -> bool:
    """Okuyan araç düzenleme bayrağıyla mı çağrılmış? (`sed -i`, `perl -pi`, `find -delete`)"""
    if name == "sed":
        return any(a.startswith(("-i", "--in-place")) for a in arguments)
    if name == "perl":
        return any(re.match(r"^-[a-zA-Z]*i", a) for a in arguments)
    if name in {"awk", "gawk"}:
        return "inplace" in arguments or any(a.startswith("--inplace") for a in arguments)
    if name == "find":
        return any(a in _FIND_EDITING for a in arguments)
    if name == "curl":
        return any(a in _CURL_OUTPUT or a.startswith("--output=") for a in arguments)
    return False


def _git_subcommand(arguments: list[str]) -> str:
    """Genel seçenekleri (`-C dizin`, `-c a=b`, `--no-pager`) atlayıp git alt komutu."""
    rest = list(arguments)
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in _GIT_VALUE_OPTIONS else rest[1:]
    return rest[0] if rest else ""


def _shell_script(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments[:-1]):
        if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", argument):
            return arguments[index + 1]
    return None


def _plan_safe(parts: list[str]) -> bool:
    """Parça salt okunur mu ya da bilinen, kaynağı düzenlemeyen bir derleme/test komutu mu?"""
    name, arguments = parts[0].rsplit("/", 1)[-1], parts[1:]
    if reads_only_words(parts):
        return True
    if any(_FIX_FLAGS.match(argument) for argument in arguments):
        return False
    if name in {"python", "python3"}:
        return arguments[:1] == ["-m"] and arguments[1:2] in ([m] for m in _PYTHON_MODULES)
    if name not in _BUILD_COMMANDS:
        return False
    allowed = _BUILD_COMMANDS[name]
    if allowed is None:
        return True
    sub = next((a for a in arguments if not a.startswith("-")), "")
    if sub not in allowed:
        return False
    if sub == "run":
        script = next((a for a in arguments[arguments.index("run") + 1 :] if a[:1] != "-"), "")
        return script in _RUN_SCRIPTS
    return True
