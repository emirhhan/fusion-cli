"""Beceri gövdesindeki `!`cmd`` ve ` ```! ` dinamik bağlamı (Claude Code kuralları, #168).

Claude Code:
- satır içi biçim yalnız `!` satır başında ya da boşluktan hemen sonra gelirse tanınır
  (`KEY=!`cmd`` düz metin kalır); çok satırlı komut ` ```! ` çitli bloğuyla yazılır;
- yerine koyma özgün metin üzerinde BİR KEZ yapılır, çıktı yeniden taranmaz;
- komut Bash aracının 2 dakikalık zaman aşımıyla koşar;
- başarısız komut (sıfır olmayan çıkış; arama/karşılaştırma komutlarının 1 kodu hariç) TÜM
  çağrıyı iptal eder, model beceri içeriğini hiç görmez;
- komut hiç onay sormaz: izin kurallarıyla denetlenir; deny eşleşmesi ya da (otomatik kip
  dışında) allow olmayan karar çağrıyı `Shell command permission check failed for pattern
  "..."` hatasıyla iptal eder; `allowed-tools` ön onayı bunu önler;
- `disableSkillShellExecution: true` her komutu `[shell command execution disabled by
  policy]` metniyle değiştirir (paketli ve kurumsal beceriler hariç).

Fusion farkı yok sayılmaz: izinli kipte (auto/acceptEdits/bypass) açık kural olmadan koşan
komut yine `run_shell` tehlike denetiminden ve otomatik kip risk analizinden geçer; proje
kaynaklı becerinin yalnız salt-okur komut koşabilmesi kısıtı da yalnız açık izin kuralı/ön
onay olmayan komutta kalır.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import FusionError
from ..core.redaction import redact
from .auto_policy import auto_risk, is_read_only_command
from .safety import danger_reason

#: Claude Code Bash aracının varsayılan zaman aşımı (saniye).
SHELL_CONTEXT_TIMEOUT_S = 120.0

#: Komut çıktısı başına en fazla karakter (bağlamı tek komutun boğmaması için).
MAX_SHELL_OUTPUT_CHARS = 2_000

#: `disableSkillShellExecution` açıkken komutun yerine konan metin (Claude ile aynı).
DISABLED_TEXT = "[shell command execution disabled by policy]"

#: 1 çıkış kodu "eşleşme yok/fark var" demek olan komutlar: hata sayılmaz.
_EXIT_ONE_OK = frozenset({"grep", "egrep", "fgrep", "rg", "ag", "diff", "cmp", "test", "["})

#: Satır içi: satır başı ya da boşluktan sonra `!`; çitli: ```! … ```.
_INLINE = re.compile(r"(?:(?<=\s)|^)!`([^`\n]+)`", re.MULTILINE)
_FENCED = re.compile(r"^```!\s*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)
_COMBINED = re.compile(f"{_FENCED.pattern}|{_INLINE.pattern}", re.MULTILINE | re.DOTALL)


class SkillShellError(FusionError):
    """`!`cmd`` başarısız ya da izinsiz: beceri çağrısı iptal edilir."""


@dataclass(frozen=True, slots=True)
class ShellPolicy:
    """Bir beceri çağrısında komutların nasıl denetleneceği."""

    #: Onay kipi komut çalıştırmaya zaten izinli mi (auto/acceptEdits/bypass) ve kök güvenilir mi.
    mode_allows: bool = False
    #: Açık kural yokken yalnız salt-okur komut (güvenilen proje becerisi).
    read_only: bool = False
    #: `disableSkillShellExecution` (paketli/kurumsal becerilerde çağıran `False` verir).
    disabled: bool = False
    #: İzin kuralı değerlendirici: `"allow" | "deny" | "ask" | None` (kural yok).
    rule_decision: Callable[[str], str | None] | None = None
    #: `allowed-tools` içindeki `Bash(...)` ön onay desenleri (`*` joker).
    preapproved: tuple[str, ...] = ()
    #: `shell:` alanı: `bash` (varsayılan) ya da `powershell`.
    shell: str = "bash"
    timeout_s: float = SHELL_CONTEXT_TIMEOUT_S


def failure_message(command: str) -> str:
    return f'Shell command permission check failed for pattern "{command}"'


def _preapproved(command: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        spec = pattern.strip()
        if spec in ("*", ""):
            return True
        prefix = spec[:-2].rstrip() if spec.endswith(":*") else None
        if prefix is not None and (command == prefix or command.startswith(prefix + " ")):
            return True
        regex = "^" + ".*".join(re.escape(part) for part in spec.split("*")) + "$"
        if re.match(regex, command, re.DOTALL):
            return True
    return False


def bash_patterns(allowed_tools: tuple[str, ...]) -> tuple[str, ...]:
    """`allowed-tools` içindeki `Bash(...)` desenleri; yalın `Bash` → hepsi (`*`)."""
    found: list[str] = []
    for entry in allowed_tools:
        name, _, rest = entry.partition("(")
        if name.strip() != "Bash":
            continue
        found.append(rest[:-1].strip() if rest.endswith(")") else "*")
    return tuple(found)


def check_command(command: str, *, cwd: Path, policy: ShellPolicy) -> None:
    """Komut koşabilir mi? Koşamazsa `SkillShellError` (çağrı iptal)."""
    decision = policy.rule_decision(command) if policy.rule_decision is not None else None
    if decision == "deny":
        raise SkillShellError(failure_message(command))
    if _preapproved(command, policy.preapproved) or decision == "allow":
        return
    if not policy.mode_allows:
        raise SkillShellError(failure_message(command))
    reason = danger_reason("run_shell", {"command": command}) or auto_risk(command, cwd)
    if reason is not None or decision == "ask":
        raise SkillShellError(f"{failure_message(command)} (riskli komut: {reason or 'ask'})")
    if policy.read_only and not is_read_only_command(command):
        raise SkillShellError(
            f"{failure_message(command)} (proje becerisinde açık izin kuralı olmadan yalnız "
            "salt-okur komut çalışır)"
        )


def _argv(command: str, shell: str) -> list[str] | str:
    if shell.strip().lower() != "powershell":
        return command
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if exe is None:
        raise SkillShellError("shell: powershell seçili ama PowerShell bulunamadı")
    return [exe, "-NoProfile", "-Command", command]


def _exit_ok(command: str, code: int) -> bool:
    if code == 0:
        return True
    try:
        head = shlex.split(command)[:1]
    except ValueError:
        head = command.split()[:1]
    return code == 1 and bool(head) and Path(head[0]).name in _EXIT_ONE_OK


def run_command(command: str, *, cwd: Path, policy: ShellPolicy) -> tuple[str, str]:
    """Denetle, koş, çıktıyı döndür: `(çıktı, not)`; hata/izinsizlikte `SkillShellError`."""
    check_command(command, cwd=cwd, policy=policy)
    argv = _argv(command, policy.shell)
    try:
        run = subprocess.run(
            argv,
            shell=isinstance(argv, str),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=policy.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise SkillShellError(f"!`{command}`: {policy.timeout_s:.0f} sn içinde bitmedi") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise SkillShellError(f"!`{command}`: çalıştırılamadı ({type(error).__name__})") from error
    if not _exit_ok(command, run.returncode):
        raise SkillShellError(f"!`{command}`: çıkış kodu {run.returncode}")
    output = redact(((run.stdout or "") + (("\n" + run.stderr) if run.stderr else "")).strip())
    if len(output) > MAX_SHELL_OUTPUT_CHARS:
        note = f"!`{command}`: çıktı {MAX_SHELL_OUTPUT_CHARS} karaktere kırpıldı"
        return output[:MAX_SHELL_OUTPUT_CHARS] + "\n[…kırpıldı…]", note
    return output, ""


def expand(text: str, *, cwd: Path, policy: ShellPolicy) -> tuple[str, tuple[str, ...]]:
    """Tüm `!`cmd`` ve ` ```! ` parçalarını tek geçişte çıktılarıyla değiştir."""
    notes: list[str] = []

    def replace(match: re.Match[str]) -> str:
        command = (match.group(1) if match.group(1) is not None else match.group(2)).strip()
        if policy.disabled:
            return DISABLED_TEXT
        output, note = run_command(command, cwd=cwd, policy=policy)
        if note:
            notes.append(note)
        return output

    return _COMBINED.sub(replace, text), tuple(notes)


def has_shell_context(text: str) -> bool:
    return _COMBINED.search(text) is not None
