"""İzin kuralını bir araç çağrısıyla eşleştirme (P-001).

`config/permission_rules.py` kuralı TANIMLAR; burası bir çağrının o kurala uyup
uymadığını söyler. Ayrı modül, çünkü kabuk zincirlerini bölmek `tools.auto_policy`'ye
bağlıdır ve `config` katmanı `tools`u içe aktaramaz (RULES.md katman sınırları).

Eşleme kuralları (Claude Code belgesiyle aynı):

    Bash(ön ek *)       ön ek + sözcük sınırı; `a && b` her parça için ayrı değerlendirilir
                        (Codex gibi): bir parça DENY ise bütün DENY, hepsi ALLOW ise ALLOW.
                        Alt kabuk (`$(…)`, ters tırnak) ALLOW'u düşürür, DENY'i düşürmez.
    Read(glob)          read_file/list_dir/glob/arama araçlarının `path`i
    Edit/Write(glob)    write_file/edit_file/multi_edit/create_file `path`i
                        glob: `/x` proje köküne göreli, `//x` dosya sistemi kökü, `~/x` ev,
                        `*` dizin sınırını aşmaz, `**` aşar
    WebFetch(domain:x)  `url` ana makinesi x ya da alt alanı
    Skill(x *), Agent(x *), mcp__sunucu__araç, <fusion_araç_adı>(x *)
                        ad ön eki (Bash ile aynı `*` kuralı)
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import reduce
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from ..config.permission_rules import (
    PermissionDecision,
    PermissionRule,
    PermissionRuleSet,
    stricter,
)
from ..core.tools import ToolFamily, tool_family
from .auto_policy import command_words

#: Claude'un `Read` kuralının kapsadığı Fusion araçları (okuma, listeleme, arama).
READ_TOOLS = frozenset(
    {
        "read_file",
        "view_file",
        "list_dir",
        "list_files",
        "glob",
        "grep_search",
        "search_code",
        "view_image",
    }
)
#: Claude'un `Edit`/`Write` kurallarının kapsadığı yerel dosya yazma araçları.
WRITE_TOOLS = frozenset({"write_file", "edit_file", "multi_edit", "create_file"})
#: Claude araç adı → Fusion araçları. Kabuk `tool_family` ile tanınır (takma adlar dahil).
_CLAUDE_TOOLS: dict[str, frozenset[str]] = {
    "Read": READ_TOOLS,
    "Edit": WRITE_TOOLS,
    "Write": WRITE_TOOLS,
    "MultiEdit": WRITE_TOOLS,
    "WebFetch": frozenset({"web_fetch", "download_file"}),
    "WebSearch": frozenset({"web_search"}),
    "Skill": frozenset({"read_skill", "find_skill"}),
    "Agent": frozenset({"invoke_agent", "find_agent"}),
    "Task": frozenset({"invoke_agent"}),
}
_MCP_PREFIX = "mcp__"
#: Belirteçsiz ad kalıbı için bakılan birincil argümanlar (sırayla).
_PRIMARY_ARGS = ("name", "skill", "agent", "command", "path", "url", "query")
#: Alt kabuk: içinde ne çalıştığı bilinemez; izin VERİLMEZ (yasak yine aranır).
_SUBSTITUTION = re.compile(r"\$\(|`|\$\{")


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """Eşleşen kural ve bileşik karar (zincirde en kısıtlayıcı parça)."""

    rule: PermissionRule
    decision: PermissionDecision


def evaluate(
    rules: PermissionRuleSet, tool_name: str, args: Mapping[str, object], root: Path | None
) -> RuleMatch | None:
    """Çağrıya uyan en kısıtlayıcı kural; hiç kural uymuyorsa `None`."""
    if not rules.rules:
        return None
    if tool_family(tool_name) is ToolFamily.SHELL and isinstance(args.get("command"), str):
        return _evaluate_shell(rules, tool_name, str(args["command"]), root)
    hits = [rule for rule in rules.rules if matches(rule, tool_name, args, root)]
    if not hits:
        return None
    decision = reduce(stricter, (rule.decision for rule in hits))
    return RuleMatch(next(rule for rule in hits if rule.decision is decision), decision)


def _evaluate_shell(
    rules: PermissionRuleSet, tool_name: str, command: str, root: Path | None
) -> RuleMatch | None:
    """Zincirin her parçası ayrı bakılır: bir DENY bütünü düşürür; ALLOW hepsini ister."""
    segments = [" ".join(parts) for parts in command_words(command)] or [command.strip()]
    shell_rules = [rule for rule in rules.rules if _tool_matches(rule, tool_name)]
    if not shell_rules:
        return None
    denied = _first_shell_match(shell_rules, segments, PermissionDecision.DENY)
    if denied is not None:
        return denied
    asked = _first_shell_match(shell_rules, segments, PermissionDecision.ASK)
    if asked is not None:
        return asked
    if _SUBSTITUTION.search(command):
        return None
    allowed: RuleMatch | None = None
    for segment in segments:
        hit = next(
            (
                r
                for r in shell_rules
                if r.decision is PermissionDecision.ALLOW and _spec_prefix(r, segment)
            ),
            None,
        )
        if hit is None:
            return None
        allowed = allowed or RuleMatch(hit, PermissionDecision.ALLOW)
    return allowed


def _first_shell_match(
    rules: list[PermissionRule], segments: list[str], decision: PermissionDecision
) -> RuleMatch | None:
    for rule in rules:
        if rule.decision is not decision:
            continue
        if any(_spec_prefix(rule, segment) for segment in segments):
            return RuleMatch(rule, decision)
    return None


def matches(
    rule: PermissionRule, tool_name: str, args: Mapping[str, object], root: Path | None
) -> bool:
    """Kural bu çağrıya uyuyor mu? (Kabuk zinciri için `evaluate` kullanılır.)"""
    if not _tool_matches(rule, tool_name):
        return False
    if rule.specifier is None:
        return True
    if tool_family(tool_name) is ToolFamily.SHELL:
        command = args.get("command")
        return isinstance(command, str) and _spec_prefix(rule, command.strip())
    if tool_name in READ_TOOLS or tool_name in WRITE_TOOLS:
        return _path_matches(rule.specifier, args.get("path"), root)
    if rule.specifier.startswith("domain:"):
        return _domain_matches(rule.specifier[len("domain:") :].strip(), args.get("url"))
    return _spec_prefix(rule, _primary_text(args))


def _tool_matches(rule: PermissionRule, tool_name: str) -> bool:
    if rule.tool == tool_name:
        return True
    if rule.tool == "Bash":
        return tool_family(tool_name) is ToolFamily.SHELL
    if rule.tool.startswith(_MCP_PREFIX):
        target = rule.tool[len(_MCP_PREFIX) :]
        if "__" in target:
            return _glob_name(target, tool_name)
        return tool_name.startswith(f"{target}__")
    return tool_name in _CLAUDE_TOOLS.get(rule.tool, frozenset())


def _glob_name(pattern: str, name: str) -> bool:
    """`mcp__meta__ads_create_*` gibi araç adında sondaki `*` ön ektir."""
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    return name == pattern


def _spec_prefix(rule: PermissionRule, text: str) -> bool:
    """Ön ek eşlemesi: `x *` sözcük sınırı ister, `x*` istemez, yıldızsız birebirdir."""
    spec = rule.specifier or ""
    if not spec.endswith("*"):
        return text == spec
    body = spec[:-1]
    if body.endswith(":"):  # eski `npm run test:*` yazımı
        body = body[:-1] + " "
    prefix = body.rstrip()
    if body and not body[-1].isspace():
        return text.startswith(prefix)
    if not prefix:
        return True
    return text == prefix or text.startswith(prefix + " ")


def _primary_text(args: Mapping[str, object]) -> str:
    for key in _PRIMARY_ARGS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return " ".join(str(v) for v in args.values() if isinstance(v, str))


def _domain_matches(domain: str, url: object) -> bool:
    if not domain or not isinstance(url, str):
        return False
    host = (urlsplit(url if "://" in url else f"//{url}").hostname or "").lower()
    domain = domain.lower().lstrip(".")
    return host == domain or host.endswith(f".{domain}")


def _path_matches(spec: str, raw: object, root: Path | None) -> bool:
    """Hedef yol kalıba uyuyor mu?

    Hem sözcüksel (verildiği gibi) hem çözülmüş (symlink'ler açılmış) yol denenir; biri
    uyarsa uyar. Sözcüksel yol `/tmp` → `/private/tmp` gibi farkları görmezden gelir,
    çözülmüş yol ise `proje/bag -> ~/.ssh` gibi bir bağla yasağı aşmayı önler.
    """
    if not isinstance(raw, str) or not raw.strip():
        return False
    targets = _variants(_absolute(raw, root))
    patterns = {
        _glob_regex(pattern)
        for base, rest in _glob_base(spec, root)
        for pattern in _variants(base, rest)
    }
    return any(regex.fullmatch(target) is not None for regex in patterns for target in targets)


def _absolute(raw: str, root: Path | None) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (root or Path.cwd()) / path


def _variants(base: Path, rest: str = "") -> set[str]:
    """Sözcüksel ve symlink'leri çözülmüş biçimleri (posix); çözülemeyen atlanır."""
    found = {PurePosixPath(os.path.normpath(base)).as_posix()}
    with contextlib.suppress(OSError, RuntimeError, ValueError):
        found.add(PurePosixPath(base.resolve()).as_posix())
    return {(PurePosixPath(item) / rest).as_posix() if rest else item for item in found}


def _glob_base(spec: str, root: Path | None) -> tuple[tuple[Path, str], ...]:
    """Belirteci (taban, kalan glob) çiftine çevir: `//x` kök, `~/x` ev, `/x` ve `x` proje kökü."""
    if spec.startswith("//"):
        return ((Path("/"), spec[2:]),)
    if spec.startswith("~"):
        return ((Path.home(), spec[1:].lstrip("/")),)
    return (((root or Path.cwd()), spec.lstrip("/")),)


def _glob_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**", index):
            # `**/` ve `/**` sıfır ya da daha çok dizini kapsar; sondaki `dizin/**`
            # dizinin KENDİSİNİ de kapsar (listelemek içini okumaktır).
            index += 2
            if index < len(pattern) and pattern[index] == "/":
                index += 1
                parts.append("(?:.*/)?")
            elif index == len(pattern) and parts and parts[-1] == "/":
                parts[-1] = "(?:/.*)?"
            else:
                parts.append(".*")
            continue
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return re.compile("".join(parts))
