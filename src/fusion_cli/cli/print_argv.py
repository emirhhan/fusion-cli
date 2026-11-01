"""Kök komut satırını Claude Code biçimine göre yeniden yazan Typer grubu (#275, #276, #314).

Claude'da başsız kip bir alt komut değil, kök bayraktır: `claude -p "sorgu" --output-format
json`. Kök komut konumsal bir istem de alır: `claude "sorgu"` etkileşimli oturumu o istemle
açar. Click alt komut temelli çalıştığından ikisi de doğrudan ifade edilemez; bu grup
argümanları ayrıştırmadan ÖNCE çevirir:

    fusion [kök bayraklar] -p [bayraklar] "sorgu"   →  fusion print [bayraklar] "sorgu"
    fusion [kök bayraklar] "sorgu"                 →  fusion [kök] --initial-prompt "sorgu"
    fusion -w                                        →  fusion -w <üretilen-ad>

Bilinen bir alt komut adı (ör. `fusion agent ...`, `fusion mcp ...`) ilk konumsal argüman
olduğunda hiçbir şey değişmez: alt komutların kendi `-p` seçenekleri bozulmaz.

`-p` yolunda Claude'un boşlukla çoklu değer alan bayrakları (`--allowedTools "Read" "Bash(git
*)"`) bayrak tekrarına açılır; Claude'daki gibi sonraki seçeneğe kadar gelen her değer o
bayrağındır.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import Any

from typer.core import TyperGroup

#: `-p` yolunun gizli alt komutu.
PRINT_COMMAND = "print"
#: `fusion --bg` arka plan görevini başlatan alt komut.
BACKGROUND_COMMAND = "agent"
#: Kök konumsal istemi taşıyan gizli kök seçeneği.
INITIAL_PROMPT_OPTION = "--initial-prompt"
_PRINT_FLAGS = frozenset({"-p", "--print"})
_WORKTREE_FLAGS = frozenset({"-w", "--worktree"})
#: Claude'da boşlukla birden çok değer alan bayraklar (commander `<values...>`).
#: `--plugin-dir` burada DEĞİL: Claude'da her bayrak tek yol alır (`-p --plugin-dir A "sorgu"`).
VARIADIC_OPTIONS = frozenset(
    {
        "--allowedTools",
        "--allowed-tools",
        "--disallowedTools",
        "--disallowed-tools",
        "--add-dir",
        "--mcp-config",
        "--betas",
    }
)


def generated_worktree_name() -> str:
    """`-w` değersiz verildiğinde (Claude ad üretir) kullanılacak kısa ad."""
    return f"wt-{secrets.token_hex(3)}"


def _value_options(group: TyperGroup) -> frozenset[str]:
    # typer 0.27 kendi click kopyasını taşır (`typer._click`): sınıf değil özellik denetlenir.
    names: set[str] = set()
    for param in group.params:
        if getattr(param, "param_type_name", "") != "option":
            continue
        if not getattr(param, "is_flag", False) and not getattr(param, "count", False):
            names.update(param.opts)
            names.update(param.secondary_opts)
    return frozenset(names)


def _first_positional(args: Sequence[str], value_options: frozenset[str]) -> int | None:
    """Kök düzeyindeki ilk konumsal argümanın sırası; yoksa None."""
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return index + 1 if index + 1 < len(args) else None
        if token.startswith("-") and token != "-":
            if _takes_value(args, index, value_options):
                index += 1
            index += 1
            continue
        return index
    return None


def _takes_value(args: Sequence[str], index: int, value_options: frozenset[str]) -> bool:
    token = args[index]
    if token in _WORKTREE_FLAGS:
        return _has_value(args, index)
    return "=" not in token and token in value_options


def _has_value(args: Sequence[str], index: int) -> bool:
    return index + 1 < len(args) and not args[index + 1].startswith("-")


def fill_worktree_names(args: Sequence[str], *, print_mode: bool = False) -> list[str]:
    """Değersiz `-w/--worktree` arkasına üretilmiş ad (#314), `--debug`a `all` koy (#305)."""
    out: list[str] = []
    for index, token in enumerate(args):
        out.append(token)
        if token in _WORKTREE_FLAGS and not _has_value(args, index):
            out.append(generated_worktree_name())
        elif print_mode and token == "--debug" and not _has_value(args, index):
            out.append("all")
    return out


def expand_variadic(args: Sequence[str]) -> list[str]:
    """`--allowedTools A B --x` → `--allowedTools A --allowedTools B --x` (#287, #303)."""
    out: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        out.append(token)
        index += 1
        if token not in VARIADIC_OPTIONS:
            continue
        first = True
        while index < len(args) and not args[index].startswith("-"):
            if not first:
                out.append(token)
            out.append(args[index])
            first = False
            index += 1
    return out


def rewrite_root_args(args: Sequence[str], group: TyperGroup) -> list[str]:
    """Kök argümanlarını Claude biçiminden Fusion'ın alt komut biçimine çevir."""
    tokens = list(args)
    if not tokens:
        return tokens
    position = _first_positional(tokens, _value_options(group))
    if position is not None and tokens[position] in group.commands:
        return tokens
    if any(token in _PRINT_FLAGS for token in tokens):
        rest = [token for token in tokens if token not in _PRINT_FLAGS]
        return [PRINT_COMMAND, *expand_variadic(fill_worktree_names(rest, print_mode=True))]
    if "--bg" in tokens:
        # `fusion --bg "görev"` (Claude kök bayrağı, #311): arka plan görevi başlatılır.
        return [BACKGROUND_COMMAND, *fill_worktree_names(tokens)]
    tokens = fill_worktree_names(tokens)
    position = _first_positional(tokens, _value_options(group))
    if position is None:
        return tokens
    prompt = tokens[position]
    return [*tokens[:position], INITIAL_PROMPT_OPTION, prompt, *tokens[position + 1 :]]


class ClaudeArgsGroup(TyperGroup):
    """Kök Typer grubu: argümanları ayrıştırmadan önce `rewrite_root_args` uygular."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:  # noqa: ANN401
        if not ctx.resilient_parsing:
            args = rewrite_root_args(args, self)
        return super().parse_args(ctx, args)
