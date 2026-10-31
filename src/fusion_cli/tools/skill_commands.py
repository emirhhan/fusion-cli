"""Slash ile çağrılan beceri/komut dosyaları: keşif, şablonlama, dinamik bağlam (P-019, P-020).

Claude Code'da `.claude/commands/x.md` ve `.claude/skills/x/SKILL.md` aynı `/x` komutunu
üretir; gövdede `$ARGUMENTS`, `$1..$N`, `${CLAUDE_SKILL_DIR}` gibi değişkenler ve `!`cmd``
ile komut çıktısı yerleştirilir. Fusion aynı dosyaları okur ve Türkçe karşılıklarını da
kabul eder (`${FUSION_SKILL_DIR}`, `${FUSION_PROJECT_DIR}`, `${FUSION_SESSION_ID}`).

Güvenlik: `!`cmd`` yalnız çağıran "izinli" dediğinde çalışır (güvenilir kök + onay kipi;
bkz. `cli/repl/skill_commands.shell_context_policy`); izinsizse yerinde not bırakılır. Çıktı
`MAX_SHELL_OUTPUT_CHARS` ile sınırlanır ve sırlar maskelenir.

Ölçüldü (31 Ekim): izinli kökte komut düz `subprocess.run` ile koşuyor, `run_shell`'in
tehlike denetimi (`danger_reason`) ve otomatik kip risk analizi (`auto_risk`) atlanıyordu;
proje becerisinde güven yalnız `.fusion/config.yaml` özetine bağlıydı, beceri dosyası `git
pull` ile değişse de tam yetkiyle çalışıyordu. Artık her komut aynı politika denetiminden
geçer (riskli komut hiç koşmaz, onay kartı sorulamadığı için yerinde not kalır) ve proje
kaynaklı beceride yalnız salt-okur komutlar (`is_read_only_command`) çalışır.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.redaction import redact
from .auto_policy import auto_risk, is_read_only_command
from .frontmatter import body_after_frontmatter, parse_frontmatter
from .safety import danger_reason

#: Komut dosyası kökleri: (ev/kök altı yol, kaynak etiketi, ev dizininde mi).
COMMAND_ROOTS: tuple[tuple[str, str, bool], ...] = (
    (".claude/commands", "claude", True),
    (".fusion/commands", "fusion", True),
    (".claude/commands", "proje", False),
    (".fusion/commands", "proje", False),
)

#: `!`cmd`` çıktısı başına en fazla karakter.
MAX_SHELL_OUTPUT_CHARS = 2_000

#: `!`cmd`` için zaman aşımı (saniye).
SHELL_CONTEXT_TIMEOUT_S = 10.0

#: Kullanıcı argüman vermediğinde becerinin görev metni (masaüstü `DEFAULT_SKILL_TASK` ile aynı).
DEFAULT_SKILL_TASK = "{name} becerisini bu görev için uygula."

#: Açıklaması olmayan komut dosyasında gövdenin ilk satırından alınacak en fazla karakter.
_SUMMARY_CHARS = 120

_SHELL_PATTERN = re.compile(r"!`([^`\n]+)`")
_POSITIONAL = re.compile(r"\$ARGUMENTS\[(\d+)\]|\$(\d+)\b")
_ESCAPED_DOLLAR = "\x00dolar\x00"


@dataclass(frozen=True, slots=True)
class TemplateEnv:
    """Şablon değişkenlerinin kaynağı."""

    skill_dir: Path
    project_dir: Path
    session_id: str = ""


@dataclass(frozen=True, slots=True)
class SkillInvocation:
    """`/beceri argüman` çağrısının tura çevrilmiş hâli."""

    #: Kullanıcı mesajı olarak gidecek görev.
    task: str
    #: Sistem bağlamına eklenecek beceri gövdesi (komut dosyasında boş: gövde görevdir).
    context: str = ""
    #: `allowed-tools` → Fusion araç adları; `None` = kısıt yok.
    allowed_tools: set[str] | None = None
    model: str = ""
    effort: str = ""
    fork: bool = False
    notes: tuple[str, ...] = ()


def discover_commands(home: Path | None, root: Path) -> tuple[object, ...]:
    """`.claude/commands/**/*.md` dosyalarını `komut` türünde `Capability` olarak döndür.

    `frontend/component.md` → `frontend:component`. Açıklama frontmatter `description`,
    yoksa gövdenin ilk dolu satırı.
    """
    # Döngüsel içe aktarma: `capabilities` bu modülü kullanır; tip burada tembel alınır.
    from .capabilities import Capability

    found: list[Capability] = []
    for rel, source, in_home in COMMAND_ROOTS:
        if in_home and home is None:
            continue
        base = (home if in_home and home is not None else root) / rel
        if not base.is_dir():
            continue
        bound = base.resolve()
        for path in sorted(base.rglob("*.md")):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            # Proje kökündeki sembolik bağ kök dışına çıkıyorsa okunmaz (depo içeriği).
            if source == "proje" and not resolved.is_relative_to(bound):
                continue
            name = ":".join(path.relative_to(base).with_suffix("").parts)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fields = parse_frontmatter(text)
            found.append(
                Capability(
                    name=str(fields.get("name") or name),
                    description=str(fields.get("description") or _first_line(text)),
                    path=path,
                    source=source,
                    kind="komut",
                    allowed_tools=_tuple(fields.get("allowed_tools")),
                    model=str(fields.get("model") or ""),
                    effort=str(fields.get("effort") or ""),
                    context=str(fields.get("context") or ""),
                    model_invocable=bool(fields.get("model_invocable", True)),
                    user_invocable=bool(fields.get("user_invocable", True)),
                    argument_hint=str(fields.get("argument_hint") or ""),
                )
            )
    return tuple(found)


def _tuple(value: object) -> tuple[str, ...]:
    return tuple(value) if isinstance(value, tuple) else ()


def _first_line(text: str) -> str:
    for line in body_after_frontmatter(text).splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned[:_SUMMARY_CHARS]
    return ""


# --- Şablon ---------------------------------------------------------------------- #


def render_template(text: str, argument: str, env: TemplateEnv) -> str:
    """`$ARGUMENTS`, `$ARGUMENTS[N]` (0 tabanlı), `$N` (1 tabanlı) ve `${…_DIR}` değişkenleri.

    Şablonda hiç argüman yer tutucusu yoksa ve argüman verildiyse argüman sona eklenir
    (Claude Code davranışı). `\\$` kaçışı dolar işaretini korur.
    """
    argument = argument.strip()
    try:
        parts = shlex.split(argument) if argument else []
    except ValueError:  # kapanmamış tırnak: boşlukla böl
        parts = argument.split()
    text = text.replace("\\$", _ESCAPED_DOLLAR)
    has_placeholder = "$ARGUMENTS" in text or _POSITIONAL.search(text) is not None

    def positional(match: re.Match[str]) -> str:
        zero_based, one_based = match.group(1), match.group(2)
        index = int(zero_based) if zero_based is not None else int(one_based) - 1
        return parts[index] if 0 <= index < len(parts) else ""

    # Önce `$ARGUMENTS[N]`/`$N`, sonra düz `$ARGUMENTS` (alt dizesi olduğu için sıra önemli).
    text = _POSITIONAL.sub(positional, text).replace("$ARGUMENTS", argument)
    for names, value in (
        (("FUSION_SKILL_DIR", "CLAUDE_SKILL_DIR"), str(env.skill_dir)),
        (("FUSION_PROJECT_DIR", "CLAUDE_PROJECT_DIR"), str(env.project_dir)),
        (("FUSION_SESSION_ID", "CLAUDE_SESSION_ID"), env.session_id),
    ):
        for name in names:
            text = text.replace("${" + name + "}", value)
    text = text.replace(_ESCAPED_DOLLAR, "$")
    if not has_placeholder and argument:
        text = f"{text.rstrip()}\n\nARGÜMANLAR: {argument}"
    return text


# --- !`cmd` dinamik bağlam -------------------------------------------------------- #


def shell_context_block_reason(command: str, *, cwd: Path, read_only: bool) -> str | None:
    """Komut neden koşmamalı? `run_shell` ile aynı denetim; sorun yoksa `None`.

    Onay kartı burada sorulamaz (tur henüz başlamadı), bu yüzden `run_shell`'de "sor"
    anlamına gelen her gerekçe burada "koşma" demektir.
    """
    reason = danger_reason("run_shell", {"command": command}) or auto_risk(command, cwd)
    if reason is not None:
        return f"riskli komut ({reason})"
    if read_only and not is_read_only_command(command):
        return "proje becerisinde yalnız salt-okur komut çalışır"
    return None


def expand_shell_context(
    text: str,
    *,
    cwd: Path,
    allowed: bool,
    read_only: bool = False,
    timeout_s: float = SHELL_CONTEXT_TIMEOUT_S,
) -> tuple[str, tuple[str, ...]]:
    """`!`cmd`` parçalarını komut çıktısıyla değiştir; izin yoksa yerinde not bırak.

    `read_only=True` (proje kaynaklı beceri): yalnız okuyan komutlar koşar.
    """
    notes: list[str] = []

    def replace(match: re.Match[str]) -> str:
        command = match.group(1).strip()
        if not allowed:
            notes.append(f"!`{command}`: dinamik bağlam bu kipte/kökte çalıştırılmadı")
            return f"[komut çalıştırılmadı: {command}]"
        blocked = shell_context_block_reason(command, cwd=cwd, read_only=read_only)
        if blocked is not None:
            notes.append(f"!`{command}`: {blocked}; çalıştırılmadı")
            return f"[komut çalıştırılmadı: {command}]"
        try:
            # Politika denetimi yukarıda (`shell_context_block_reason`); `allowed` kapısı da.
            run = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            notes.append(f"!`{command}`: çalıştırılamadı ({type(error).__name__})")
            return f"[komut çalıştırılamadı: {command}]"
        output = (run.stdout or "") + (("\n" + run.stderr) if run.stderr else "")
        output = redact(output.strip())
        if len(output) > MAX_SHELL_OUTPUT_CHARS:
            notes.append(f"!`{command}`: çıktı {MAX_SHELL_OUTPUT_CHARS} karaktere kırpıldı")
            output = output[:MAX_SHELL_OUTPUT_CHARS] + "\n[…kırpıldı…]"
        return output

    return _SHELL_PATTERN.sub(replace, text), tuple(notes)


# --- Çağrı ----------------------------------------------------------------------- #


def build_invocation(
    capability: object,
    argument: str,
    env: TemplateEnv,
    *,
    shell_allowed: bool,
    shell_read_only: bool = False,
) -> SkillInvocation:
    """`Capability` + argümanı tura çevir (komut: görev; beceri: bağlam + görev)."""
    from .capabilities import Capability, map_tools

    assert isinstance(capability, Capability)
    try:
        raw = capability.path.read_text(encoding="utf-8")
    except OSError as error:
        return SkillInvocation(task=argument, notes=(f"beceri okunamadı: {error}",))
    body = body_after_frontmatter(raw).replace("{SKILL_DIR}", str(capability.path.parent))
    rendered = render_template(body, argument, env)
    rendered, notes = expand_shell_context(
        rendered, cwd=env.project_dir, allowed=shell_allowed, read_only=shell_read_only
    )
    allowed_tools: set[str] | None = None
    if capability.allowed_tools:
        # `Bash(git *)` biçiminde komut deseni: araç adı eşlenir, desen kısıtı Fusion'da
        # komut politikasıyla değil onay kipiyle yönetilir; bu not modele değil kullanıcıya.
        names = tuple(name.split("(", 1)[0].strip() for name in capability.allowed_tools)
        allowed_tools = map_tools(names)
        if any("(" in name for name in capability.allowed_tools):
            notes = (*notes, "allowed-tools içindeki komut deseni (örn. Bash(git *)) uygulanmadı")
    fork = capability.context.strip().lower() == "fork"
    if capability.kind == "komut":
        return SkillInvocation(
            rendered, "", allowed_tools, capability.model, capability.effort, fork, notes
        )
    context = (
        f'<beceri ad="{capability.name}" kaynak="{capability.source}">\n'
        "Kullanıcının açıkça seçtiği beceri; bu turda yönergeleri uygula.\n"
        f"{rendered}\n</beceri>"
    )
    task = argument.strip() or DEFAULT_SKILL_TASK.format(name=capability.name)
    return SkillInvocation(
        task, context, allowed_tools, capability.model, capability.effort, fork, notes
    )
