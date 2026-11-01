"""Kabul başlangıcını aday importlarından ayıran saf komut planı."""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

_SHELL_OPERATORS = frozenset({"&&", "||", ";"})
_CONFIG_OPTIONS = frozenset({"-c", "--config", "--config-file", "--inifile", "--rcfile"})
_NON_PYTHON_COMMANDS = frozenset(
    {"true", "false", "sleep", "node", "rustc", "cargo", "echo", "printf", "pwd", "test"}
)
_PYTEST_COMMANDS = frozenset({"pytest", "py.test"})
_INPUT_EXPANSIONS = ("$", "`", "~", "\\", "*", "?", "[", "]")
_PYTHON_NAMES = frozenset({"python", "python3", PurePosixPath(sys.executable).name})
_BOOTSTRAP = """import importlib, os, runpy, sys
mode, target = sys.argv[1:3]
sys.argv = [target, *sys.argv[3:]]
if mode == '-m':
    if not target.startswith('evals.'):
        importlib.import_module(target)
        sys.path.insert(0, os.getcwd())
    runpy.run_module(target, run_name='__main__', alter_sys=True)
else:
    sys.path.insert(0, os.getcwd())
    if mode == '-c':
        exec(compile(target, '<kabul>', 'exec'), {'__name__': '__main__'})
    else:
        runpy.run_path(target, run_name='__main__')
"""


@dataclass(frozen=True, slots=True)
class AcceptanceCommand:
    """Çalıştırılabilir komut ve tohumdan korunacak açık kabul bağımlılıkları."""

    command: str | None
    frozen_inputs: frozenset[str] = frozenset()
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CommandChain:
    """Shell genişletmesi içermeyen alt komutlar ve açık kontrol işleçleri."""

    commands: tuple[tuple[str, ...], ...]
    operators: tuple[str, ...]


def plan_acceptance(command: str) -> AcceptanceCommand:
    """Kapalı komut gramerini çöz; belirsiz başlatıcıyı ham shell'e geçirme."""
    try:
        chain = _parse_chain(command)
        has_cd = any(arguments[0] == "cd" for arguments in chain.commands)
        if has_cd and any(operator != "&&" for operator in chain.operators):
            raise ValueError("Dizin değiştiren kabul zinciri yalnız && içerebilir.")
        rewritten = []
        frozen: set[str] = set()
        cwd = "."
        for arguments in chain.commands:
            if arguments[0] == "cd":
                if len(arguments) != 2 or arguments[1].startswith("-"):
                    raise ValueError("Kabul dizini tek bir göreli tohum yolu olmalı.")
                cwd = _relative_input(arguments[1], cwd)
                rewritten.append(shlex.join(arguments))
            else:
                frozen.update(_command_inputs(list(arguments), cwd))
                rewritten.append(shlex.join(_trusted_python(list(arguments))))
        joined = rewritten[0]
        for operator, part in zip(chain.operators, rewritten[1:], strict=True):
            joined += f" {operator} {part}"
        return AcceptanceCommand(joined, frozenset(frozen))
    except ValueError as error:
        return AcceptanceCommand(None, unavailable_reason=str(error))


def _parse_chain(command: str) -> CommandChain:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    segments: list[list[str]] = [[]]
    operators = []
    for token in lexer:
        if token in _SHELL_OPERATORS:
            operators.append(token)
            segments.append([])
        elif token and all(char in "&|;<>()" for char in token):
            raise ValueError("Kabul komutunun shell işleci desteklenmiyor.")
        else:
            segments[-1].append(token)
    if any(not segment for segment in segments):
        raise ValueError("Kabul komutu boş bir alt komut içeriyor.")
    return CommandChain(tuple(tuple(segment) for segment in segments), tuple(operators))


def _trusted_python(arguments: list[str]) -> list[str]:
    executable, *options = arguments
    if "=" in executable:
        raise ValueError("Kabul komutunda ortam ataması desteklenmiyor.")
    if executable in _PYTEST_COMMANDS:
        return _trusted_python(["python", "-m", "pytest", *options])
    if PurePosixPath(executable).name not in _PYTHON_NAMES:
        if executable not in _NON_PYTHON_COMMANDS:
            raise ValueError("Kabul başlatıcısı desteklenen komut gramerinde değil.")
        return arguments
    if not options:
        raise ValueError("Kabul Python komutunun çalıştırma hedefi eksik.")
    if options[0] in {"-m", "-c"} and len(options) >= 2:
        mode, target, *tail = options
    elif not options[0].startswith("-"):
        mode, target, tail = "script", options[0], options[1:]
    else:
        raise ValueError("Kabul Python seçenekleri güvenilir başlangıçta desteklenmiyor.")
    return [sys.executable, "-P", "-c", _BOOTSTRAP, mode, target, *tail]


def _command_inputs(arguments: list[str], cwd: str) -> set[str]:
    """Açık config ve pytest dosya hedefleri ada bakılmadan korunur."""
    options = arguments[1:]
    is_python = PurePosixPath(arguments[0]).name in _PYTHON_NAMES
    if options[:1] == ["-c"] and is_python:
        return set()
    is_pytest = PurePosixPath(arguments[0]).name in _PYTEST_COMMANDS
    if options[:1] == ["-m"]:
        is_pytest = options[1:2] == ["pytest"]
        options = options[2:]
    inputs = set()
    for index, option in enumerate(options):
        key, separator, value = option.partition("=")
        if is_pytest and option.startswith("-c") and len(option) > 2 and not separator:
            key, separator, value = "-c", "=", option[2:]
        if key in _CONFIG_OPTIONS:
            if not separator:
                if index + 1 >= len(options):
                    raise ValueError("Kabul yapılandırma yolu eksik.")
                value = options[index + 1]
            inputs.add(_relative_input(value, cwd))
        elif is_pytest and not option.startswith("-"):
            target = option.split("::", 1)[0]
            if PurePosixPath(target).suffix == ".py":
                inputs.add(_relative_input(target, cwd))
    return inputs


def _relative_input(value: str, cwd: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or any(marker in value for marker in _INPUT_EXPANSIONS)
    ):
        raise ValueError("Kabul girdisi tohum kökü içinde olmalı.")
    return str(PurePosixPath(cwd) / path)
