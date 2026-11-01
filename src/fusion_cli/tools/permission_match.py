"""İzin kuralını bir araç çağrısıyla eşleştirme (P-001).

`config/permission_rules.py` kuralı TANIMLAR; burası bir çağrının o kurala uyup
uymadığını söyler. Ayrı modül, çünkü kabuk zincirlerini bölmek `tools.auto_policy`'ye
bağlıdır ve `config` katmanı `tools`u içe aktaramaz (RULES.md katman sınırları).

Eşleme kuralları (Claude Code belgesiyle aynı):

    Bash(ön ek *)       ön ek + sözcük sınırı; `a && b` her parça için ayrı değerlendirilir
                        (Codex gibi): bir parça DENY ise bütün DENY, hepsi ALLOW ise ALLOW.
                        Alt kabuk (`$(…)`, ters tırnak) ALLOW'u düşürür, DENY'i düşürmez.
                        Sarmalayıcı (`sh -c '…'`, `timeout 5 …`, `sudo …`, `eval …`) ve
                        mutlak yol (`/bin/rm`) açılır: iç komut da parça sayılır. Dosyaya
                        yönlendirme (`> x`, `>> x`, `| tee x`) ALLOW'u düşürür (kısmi komut
                        izni dosya yazma izni değildir), DENY/ASK'i düşürmez.
    Read(glob)          read_file/list_dir/glob/arama araçlarının `path`i; arama/listeleme
                        aracında `path` yoksa kök alınır ve deny/ask kuralının kapsamı
                        aramanın kapsamına GİRİYORSA kural uyar (arama yasak dosyadan satır
                        döndürmesin); allow bu yoldan genişlemez
    Edit/Write(glob)    yerel yola yazan araçların hedefi (`write_targets`: write_file,
                        edit_file, download_file, extract_archive, görsel araçları…)
                        glob: `/x` proje köküne göreli, `//x` dosya sistemi kökü, `~/x` ev,
                        `*` dizin sınırını aşmaz, `**` aşar
    WebFetch(domain:x)  `url` ana makinesi x ya da alt alanı
    Cd(glob)            `/cd` komutunun hedef dizini (P-072); `Edit` ile aynı glob kuralı
    Skill(x *), Agent(x *), mcp__sunucu__araç, <fusion_araç_adı>(x *)
                        ad ön eki (Bash ile aynı `*` kuralı)
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
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
from .auto_policy import command_words, nested_command, written_files
from .write_targets import WRITE_TOOLS, write_targets

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
#: Dizin kapsamıyla çalışan okuma araçları: `path` verilmezse proje kökünün tamamı.
_SCOPE_READ_TOOLS = frozenset({"list_dir", "list_files", "glob", "grep_search", "search_code"})
#: Claude araç adı → Fusion araçları. Kabuk `tool_family` ile tanınır (takma adlar dahil).
_CLAUDE_TOOLS: dict[str, frozenset[str]] = {
    "Read": READ_TOOLS,
    "Edit": WRITE_TOOLS,
    "Write": WRITE_TOOLS,
    "MultiEdit": WRITE_TOOLS,
    "WebFetch": frozenset({"web_fetch", "download_file"}),
    "WebSearch": frozenset({"web_search"}),
    "Skill": frozenset({"read_skill", "find_skill"}),
    # Claude Monitor: komut izlemesi Bash kurallarına da tabidir; ws izlemesi yalnız buna (#336).
    "Monitor": frozenset({"monitor"}),
    # Çekirdekte alt ajan araçları `spawn_agent`/`spawn_agents`tır (ölçüldü, 31 Ekim:
    # yalnız `invoke_agent` bağlıydı, `Agent(*)` deny hiçbir şeyle eşleşmiyordu).
    "Agent": frozenset(
        {
            "Agent",
            "Task",
            "invoke_subagent",
            "spawn_agent",
            "spawn_agents",
            "invoke_agent",
            "find_agent",
        }
    ),
    "Task": frozenset(
        {"Agent", "Task", "invoke_subagent", "spawn_agent", "spawn_agents", "invoke_agent"}
    ),
}
_MCP_PREFIX = "mcp__"
#: `/cd` hedefinin kural adı (Claude Code `Cd`); araç değil, REPL komutudur (P-072).
CD_RULE_TOOL = "Cd"
#: Belirteçsiz ad kalıbı için bakılan birincil argümanlar (sırayla).
_PRIMARY_ARGS = ("name", "skill", "agent", "command", "path", "url", "query")
#: Alt kabuk: içinde ne çalıştığı bilinemez; izin VERİLMEZ (yasak yine aranır).
_SUBSTITUTION = re.compile(r"\$\(|`|\$\{")
#: Yetki yükselten sarmalayıcılar ve değer alan seçenekleri (`sudo -u root rm x`).
_PRIVILEGE_WRAPPERS: dict[str, frozenset[str]] = {
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-T", "-U", "--user"}),
    "doas": frozenset({"-u", "-C"}),
}
#: Sarmalayıcı açma derinliği (`auto_policy._MAX_NESTING` ile aynı).
_MAX_NESTING = 4
#: Yazma sayılmayan yönlendirme hedefi.
_NULL_DEVICE = "/dev/null"
#: Çöpe/hataya yönlendirme: parçalamadan önce atılır (`2>&1` `&`ten bölünüp `1` parçası üretiyordu).
_NULL_REDIRECTS = re.compile(r"\d?>\s*/dev/null|2>&1|&>\s*/dev/null")


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
    """Zincirin her parçası ayrı bakılır: bir DENY bütünü düşürür; ALLOW hepsini ister.

    Ölçüldü (31 Ekim): parçalar olduğu gibi ön ek eşleniyordu; `deny: Bash(rm *)` varken
    `bash -c 'rm -rf x'`, `timeout 5 rm x`, `/bin/rm x` yasağı bulmuyor, bypass kipinde
    çalışıyordu. `allow: Bash(ls *)` ise `ls >> ~/.ssh/authorized_keys` komutunu da
    `pre_allowed` yapıp kip/risk denetimini atlatıyordu.
    """
    segments = shell_segments(command)
    shell_rules = [rule for rule in rules.rules if _tool_matches(rule, tool_name)]
    if not shell_rules:
        return None
    denied = _first_shell_match(shell_rules, segments, PermissionDecision.DENY)
    if denied is not None:
        return denied
    asked = _first_shell_match(shell_rules, segments, PermissionDecision.ASK)
    if asked is not None:
        return asked
    if _SUBSTITUTION.search(command) or writes_files(command):
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


def shell_segments(command: str, depth: int = 0) -> list[str]:
    """Kurala karşı denenecek parçalar: zincir parçaları + sarmalayıcıların iç komutları.

    Mutlak yollu komut adı taban adına indirilir (`/bin/rm x` → `rm x`). Boş komutta tek
    parça komutun kendisidir.
    """
    found: list[str] = []
    for parts in command_words(_NULL_REDIRECTS.sub("", command)):
        name = parts[0]
        if name.startswith("/"):
            parts = [name.rsplit("/", 1)[-1], *parts[1:]]
        found.append(" ".join(parts))
        if depth >= _MAX_NESTING:
            continue
        inner = _unwrapped(parts[0], parts[1:])
        if inner:
            found.extend(shell_segments(inner, depth + 1))
    return found or [command.strip()]


def _unwrapped(name: str, arguments: list[str]) -> str | None:
    """`sudo [-u x] komut`, `sh -c '…'`, `timeout 5 …`, `eval …` içindeki komut; yoksa None."""
    value_flags = _PRIVILEGE_WRAPPERS.get(name)
    if value_flags is None:
        return nested_command(name, arguments)
    rest = list(arguments)
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in value_flags else rest[1:]
    return " ".join(shlex.quote(part) for part in rest) or None


def writes_files(command: str) -> tuple[str, ...]:
    """Komutun dosyaya yazdığı hedefler (`> x`, `>> x`, `| tee x`); `/dev/null` sayılmaz."""
    return tuple(t for t in written_files(command) if t.strip("'\"") != _NULL_DEVICE)


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
    if rule.tool in {"Agent", "Task"}:
        tasks = args.get("gorevler")
        if isinstance(tasks, list):
            targets = [item for item in tasks if isinstance(item, Mapping)]
            hits = [matches(rule, "Agent", item, root) for item in targets]
            return (
                bool(hits) and all(hits) if rule.decision is PermissionDecision.ALLOW else any(hits)
            )
        target = args.get("subagent_type", args.get("uzman", args.get("agent", "")))
        if tool_name == "invoke_agent":
            # Eski `invoke_agent` tipi `name` ile alır; `Agent`taki `name` ekip üyesi adıdır.
            target = args.get("name", target)
        return isinstance(target, str) and _spec_prefix(rule, target)
    if tool_family(tool_name) is ToolFamily.SHELL:
        command = args.get("command")
        return isinstance(command, str) and _spec_prefix(rule, command.strip())
    if tool_name in WRITE_TOOLS:
        return any(
            _path_matches(rule.specifier, raw, root) for raw in write_targets(tool_name, args)
        )
    if tool_name in READ_TOOLS:
        return _read_matches(rule, tool_name, args, root)
    if tool_name == CD_RULE_TOOL:
        return _path_matches(rule.specifier, args.get("path"), root)
    if rule.specifier.startswith("domain:"):
        return _domain_matches(rule.specifier[len("domain:") :].strip(), args.get("url"))
    return _spec_prefix(rule, _primary_text(args))


def _read_matches(
    rule: PermissionRule, tool_name: str, args: Mapping[str, object], root: Path | None
) -> bool:
    """`Read` kuralı: hedef yol kalıba uyar; arama/listelemede kalıp aramanın kapsamına girer.

    Ölçüldü (31 Ekim): `deny: Read(/sec/**)` varken `search_code {query}` (path'siz) ya da
    `grep_search` kök genelinde `sec/` içinden satır döndürüyordu; kural yalnız `path`e
    bakıyordu. Kısıtlayıcı (deny/ask) kural için aramanın dizini kalıbın tabanını kapsıyorsa
    kural uyar; allow kuralı bu yoldan GENİŞLEMEZ (izin yalnız hedefin kendisine verilir).
    """
    spec = rule.specifier or ""
    raw = args.get("path")
    scope = raw if isinstance(raw, str) and raw.strip() else None
    if scope is None and tool_name not in _SCOPE_READ_TOOLS:
        return False
    target = scope if scope is not None else "."
    if _path_matches(spec, target, root):
        return True
    if tool_name not in _SCOPE_READ_TOOLS or rule.decision is PermissionDecision.ALLOW:
        return False
    return _scope_covers(spec, target, root)


def _scope_covers(spec: str, scope: str, root: Path | None) -> bool:
    """Kalıbın glob'suz tabanı (`/sec/**` → `<kök>/sec`) arama dizininin altında mı?"""
    scope_dirs = _variants(_absolute(scope, root))
    for base, rest in _glob_base(spec, root):
        literal = rest.split("*", 1)[0].split("?", 1)[0]
        literal = literal.rsplit("/", 1)[0] if "/" in literal else literal
        for pattern_dir in _variants(base, literal):
            if any(
                pattern_dir == scope_dir or pattern_dir.startswith(scope_dir.rstrip("/") + "/")
                for scope_dir in scope_dirs
            ):
                return True
    return False


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
    """Ön ek eşlemesi: `x *` sözcük sınırı ister, `x*` istemez, yıldızsız birebirdir.

    Belirteçsiz kural (`Bash`, kanca kararıyla kurulan kural) aracın TÜM çağrılarına uyar.
    Ölçüldü (31 Ekim): kabuk zinciri değerlendirmesi belirteci `""` sayıyordu; `deny: Bash`
    ve PreToolUse `ask`/`allow` kararı hiçbir komutla eşleşmiyordu.
    """
    if rule.specifier is None:
        return True
    spec = rule.specifier
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
    host = (urlsplit(url if "://" in url else f"//{url}").hostname or "").lower().rstrip(".")
    domain = domain.lower().strip(".")
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


#: Kanca yükünde (`tool_name`) gösterilen birincil Claude adı (P-009); listede olmayan
#: araç kendi adıyla gider.
_CLAUDE_PRIMARY: dict[str, str] = {
    "read_file": "Read",
    "view_file": "Read",
    "write_file": "Write",
    "edit_file": "Edit",
    "multi_edit": "MultiEdit",
    "glob": "Glob",
    "grep_search": "Grep",
    "search_code": "Grep",
    "list_dir": "LS",
    "list_files": "LS",
    "web_fetch": "WebFetch",
    "web_search": "WebSearch",
    "spawn_agent": "Agent",
    "spawn_agents": "Agent",
    "invoke_agent": "Agent",
    "read_skill": "Skill",
    "todo_write": "TodoWrite",
}


def claude_tool_names(tool_name: str) -> tuple[str, ...]:
    """Fusion aracının kanca eşleştiricisinde tanınan adları: birincil Claude adı önce.

    `Bash` kabuk ailesinin hepsini (takma adlar dahil), `Edit|Write` bütün yerel yazma
    araçlarını kapsar (izin kurallarıyla aynı tablo). MCP aracı `sunucu__araç` Fusion'da,
    Claude'da `mcp__sunucu__araç` adını taşır; ikisi de eşleşir.
    """
    names: list[str] = []
    primary = _CLAUDE_PRIMARY.get(tool_name)
    if tool_family(tool_name) is ToolFamily.SHELL:
        primary = "Bash"
    if primary is not None:
        names.append(primary)
    names.extend(claude for claude, tools in _CLAUDE_TOOLS.items() if tool_name in tools)
    if "__" in tool_name and not tool_name.startswith(_MCP_PREFIX):
        names.append(f"{_MCP_PREFIX}{tool_name}")
    names.append(tool_name)
    return tuple(dict.fromkeys(names))
