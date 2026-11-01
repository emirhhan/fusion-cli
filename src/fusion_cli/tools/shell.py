"""Kabuk ve git araçları.

`git` bilinçli olarak SALT-OKUNURDUR: yalnızca beyaz listedeki alt komutlar çalışır
ve onay gerektirmez. Durum/diff/log okumak için her seferinde onay istemek kullanıcıyı
yorar; commit/push gibi değiştirici git işlemleri `run_shell` üzerinden geçer ve
oradaki onay + tehlike kontrolüne tabi olur.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import replace
from pathlib import Path

from ..config.paths import trash_dir
from ..core.constants import (
    EXIT_CODE_PREFIX,
    GIT_TIMEOUT_S,
    SHELL_TIMEOUT_S,
    truncate_notice,
)
from ..core.errors import ProcessCancelledError
from ..core.foreground_handoff import handoff_slot
from ..core.process_control import MovedToBackgroundError, run_foreground
from ..core.tools import ToolArgs, ToolContext, ToolResult
from ..core.workspace_fingerprint import (
    Fingerprint,
    WorkspaceEffect,
    launches_background_process,
    measure_effect,
    take_fingerprint,
)
from .args import require_str
from .auto_policy import is_read_only_command
from .bash_settings import output_limit, timeout_seconds, wants_background
from .command_semantics import READONLY_GIT_SUBCOMMANDS, git_reads_only
from .files import invented_path_reason
from .job_delivery import prepare_outputs
from .job_evidence import prepare_manifest
from .job_lifetime import time_limit_s
from .jobs import start_job
from .remotion_shell_guard import (
    check_shell_result,
    is_repair_command,
    remotion_integrity_error,
    repair_hint,
)
from .safe_delete import DeleteRefusedError, move_to_trash, simple_rm_targets
from .sandbox_runtime import (
    SandboxRun,
    background_exit_note,
    delete_blocked,
    prepare_sandbox,
    release_sandbox,
    sandbox_env,
    sandbox_notes,
)
from .shell_adopt import adopt, can_adopt, new_token
from .shell_output import is_benign_exit, output_limits, shape_output
from .shell_overwrite import backup_paths
from .wordpress_setup import php_env

__all__ = ["READONLY_GIT_SUBCOMMANDS", "git", "run_shell"]

#: Süreç başına bir kez gösterilen sandbox uyarıları (her komutta tekrarlanmaz).
_SHOWN_SANDBOX_NOTICES: set[str] = set()
_UNPROVEN_WRITE_NOTE = (
    "\nFUSION_NOT: Değişen dosyaların yazarı doğrulanamadı; otomatik dosya geri alma "
    "uygulanmaz, ilk kayıtları korunur."
)


def _once_notice(run: SandboxRun) -> str:
    """Sandbox kurulamadı uyarısı süreç başına bir kez."""
    notice = run.plan.notice
    if not notice or notice in _SHOWN_SANDBOX_NOTICES:
        return ""
    _SHOWN_SANDBOX_NOTICES.add(notice)
    return f"\nFUSION_NOT: {notice}"


def _sandbox_notes(run: SandboxRun, process: subprocess.CompletedProcess[str]) -> str:
    """Sandbox uyarısı (bir kez) ve engellenen yazma/okuma/ağ için eyleme dönük ipuçları."""
    notes = sandbox_notes(run, process.returncode, process.stderr)
    return _once_notice(run) + "".join(f"\nFUSION_NOT: {note}" for note in notes)


def run_shell(args: ToolArgs, context: ToolContext) -> ToolResult:
    command = require_str(args, "command")
    integrity_error = remotion_integrity_error(context)
    if integrity_error is not None and not is_repair_command(context, command):
        return ToolResult.failure(repair_hint(integrity_error))
    uydurma = _invented_path(command, context.root)
    if uydurma is not None:
        return ToolResult.failure(uydurma)
    deleted = _guarded_delete(command, context, args)
    if deleted is not None:
        return check_shell_result(context, deleted, baseline=integrity_error)
    # Ezilecek/taşınacak mevcut proje dosyaları çalışmadan ÖNCE geri alma kaydına
    # girer (T1-18). Kabukta yazarı kanıtlayan dosya makbuzu yoktur; bu kayıt
    # önceki içeriği korur ama shell farkından otomatik geri alma yetkisi doğmaz.
    for path in backup_paths(command, context.root):
        context.changes.record(path)
    if wants_background(args):
        try:
            manifest = prepare_manifest(args, context.root)
            outputs = prepare_outputs(args, context.root)
        except (OSError, ValueError) as error:
            return ToolResult.failure(f"İş kanıtı hazırlanamadı: {error}")
        run = prepare_sandbox(command, args, context)
        if run.plan.refused:
            release_sandbox(run)
            return ToolResult.failure(run.plan.refused)
        # Proxy işe aittir: iş süreci bitince kapanır (iş başlamazsa hemen).
        started: ToolResult | None = None
        try:
            started = start_job(
                command,
                context,
                sandbox_env(_shell_env(context), run),
                manifest=manifest,
                outputs=outputs,
                argv_prefix=run.plan.prefix,
                on_exit=lambda: background_exit_note(run),
                limit_s=time_limit_s(args.get("timeout")),
            )
        finally:
            if started is None or not started.ok:
                release_sandbox(run)
        notes = _once_notice(run) + "".join(
            f"\nFUSION_NOT: {note}" for note in sandbox_notes(run, 0, "")
        )
        return replace(started, output=f"{started.output}{notes}") if notes else started
    run = prepare_sandbox(command, args, context)
    token = new_token() if can_adopt(command) else None
    handed_over = False
    try:
        return _run_foreground(
            command, context, run, integrity_error, timeout_seconds(args), token=token
        )
    except MovedToBackgroundError as moved:
        # Süreç ve proxy artık işe aittir: iş bitince kapanır (#319).
        handed_over = True
        return adopt(moved, command, token or "", context, lambda: background_exit_note(run))
    finally:
        if not handed_over:
            release_sandbox(run)


def _run_foreground(
    command: str,
    context: ToolContext,
    run: SandboxRun,
    integrity_error: str | None,
    timeout_s: float = SHELL_TIMEOUT_S,
    *,
    token: str | None = None,
) -> ToolResult:
    """Komutu ön planda çalıştır; proxy'nin sahibi çağırandır (bitince kapatır).

    `token` verilirse zaman aşımında süreç öldürülmez, `MovedToBackgroundError` yükselir (#319).
    """
    if run.plan.refused:
        return ToolResult.failure(run.plan.refused)
    before, skipped = _fingerprint_before(command, context)
    try:
        # shell=True bilinçli: kullanıcı boru/yönlendirme içeren komut yazabilmeli.
        # Komut buraya gelmeden önce tehlike kontrolünden ve onay akışından geçer.
        with handoff_slot() as slot:
            process = run_foreground(
                command,
                timeout_s=timeout_s,
                cancelled=context.cancelled,
                cwd=context.root,
                env=sandbox_env(_shell_env(context), run),
                argv_prefix=run.plan.prefix,
                adopt_on_timeout=(lambda: True) if token else None,
                handoff=slot if token else None,
                ownership_marker=token,
            )
    except ProcessCancelledError as error:
        return ToolResult.failure(str(error))
    except subprocess.TimeoutExpired as timeout:
        return ToolResult.failure(_timeout_message(timeout, timeout_s))
    except OSError as exc:
        return ToolResult.failure(f"Komut çalıştırılamadı: {exc}")

    inline, window = output_limits(context.root)
    body, saved = shape_output(
        _join(process.stdout, process.stderr),
        valid=is_benign_exit(command, process.returncode),
        inline=inline,
        window=window,
        store=context.artifacts,
    )
    text = f"{EXIT_CODE_PREFIX}{process.returncode})\n{body}".strip()
    text += _sandbox_notes(run, process)
    if process.returncode != 0 and any(char.isspace() for char in str(context.root)):
        text += (
            "\nFUSION_NOT: Komut zaten seçili proje dizininde çalışır. "
            "Göreli yol kullanın; tam yol gerekiyorsa boşlukları koruyun: "
            f"{shlex.quote(str(context.root))}"
        )
    effect = skipped
    if effect is None and _measures(command, context):
        effect = measure_effect(before, context.root)
    if effect is not None and effect.changed is not None:
        changed = {context.root / relative for relative in effect.changed}
        unproven = changed.intersection(context.changes.paths)
        # Parmak izi ve çıkış kodu yazarı kanıtlamaz; kullanıcı da yazmış olabilir.
        # Değişmeyen yolun önceki doğrulanmış araç kimliği ise korunur.
        for path in unproven:
            context.changes.invalidate_applied(path)
        if unproven:
            text += _UNPROVEN_WRITE_NOTE
    return check_shell_result(
        context,
        ToolResult(
            text,
            ok=process.returncode == 0,
            workspace_effect=effect,
            artifact_path=str(saved) if saved else "",
            output_shaped=True,
        ),
        baseline=integrity_error,
    )


def _measures(command: str, context: ToolContext) -> bool:
    """Bu komut için çalışma alanı etkisi ölçülür mü (ayar açık, komut salt-okunur değil)?"""
    return getattr(context, "shell_fingerprint", True) and not is_read_only_command(command)


def _fingerprint_before(
    command: str, context: ToolContext
) -> tuple[Fingerprint | None, WorkspaceEffect | None]:
    """Komuttan ÖNCE parmak izi; ölçülemeyecekse (arka plan süreci) hazır sonuç da döner.

    Ölçüldü (30 Ekim): tanınmayan program temkinli olarak mutasyon sayılıyordu. Arka plana
    atılan süreç komut bittikten sonra da yazabileceğinden "önce/sonra" ona güvenilmez;
    eski temkinli davranış korunur.
    """
    if not _measures(command, context):
        return None, None
    if launches_background_process(command):
        return None, WorkspaceEffect(None, "arka plan süreci")
    return take_fingerprint(context.root), None


#: Argümanında çoğu kez desen/URL yolu taşıyan komutlar; yol denetimi yapılmaz.
_PATTERN_COMMANDS = frozenset({"grep", "rg", "sed", "awk", "echo", "printf", "curl", "wget", "git"})


def _invented_path(command: str, root: Path) -> str | None:
    """Komuttaki mutlak yollardan biri var olmayan bir kökteyse gerekçe."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or tokens[0].rsplit("/", 1)[-1] in _PATTERN_COMMANDS:
        return None
    for token in tokens:
        reason = invented_path_reason(token, root)
        if reason is not None:
            return reason
    return None


def _guarded_delete(command: str, context: ToolContext, args: ToolArgs) -> ToolResult | None:
    """Sade `rm` komutunu kalıcı silme yerine Fusion çöpüne taşı (bkz. `safe_delete`).

    Onay akışından SONRA, çalıştırma anında uygulanır. Sade olmayan silme
    (`find -delete`, boru, betik) REDDEDİLMEZ: onay kartı onun KALICI olduğunu
    söyler ve kullanıcı onaylarsa olduğu gibi çalışır — kullanıcı silmek istediğini
    silebilmeli.
    """
    targets = simple_rm_targets(command)
    if targets is None:
        return None
    blocked = delete_blocked(list(targets), args, context)
    if blocked is not None:
        return ToolResult.failure(blocked)
    try:
        moved, missing = move_to_trash(
            targets,
            cwd=context.root,
            root=context.root,
            home=Path.home(),
            trash_root=trash_dir(),
        )
    except DeleteRefusedError as refused:
        return ToolResult.failure(str(refused))
    except OSError as exc:
        return ToolResult.failure(f"Silinemedi (çöpe taşınamadı): {exc}")
    lines = [f"(çıkış kodu 0)\nKalıcı silinmedi; Fusion çöpüne taşındı ({len(moved)}):"]
    lines += [f"- {entry.original}  [geri al: fusion cop geri-al {entry.id}]" for entry in moved]
    if missing:
        lines.append("Zaten yoktu: " + ", ".join(missing))
    return ToolResult("\n".join(lines))


def _shell_env(context: ToolContext) -> dict[str, str]:
    """Kabuk ortamı: Homebrew PATH'i ve çalışan bir WP-CLI.

    Ölçüldü (2 Ekim, kabul koşusu): ajanın `wp core download` komutu PHP'nin 128 MB
    sınırında çöktü ve model WordPress'i curl ile elle kurmaya saptı. Kullanıcı
    kendi WP_CLI_PHP_ARGS'ını vermişse ona dokunulmaz. MCP sır adları
    (`context.hidden_env`) çıkarılır: komut `env` yazarsa sırlar modele gitmesin.
    """
    return {name: value for name, value in php_env().items() if name not in context.hidden_env}


def _timeout_message(timeout: subprocess.TimeoutExpired, timeout_s: float = SHELL_TIMEOUT_S) -> str:
    """Zaman aşımını ELDE OLAN kanıtla anlat.

    Ölçüldü: model `npm run start:all` çalıştırdı — üç servisi birlikte ayağa
    kaldıran bir dev sunucusu. O komut hiç bitmez. Dönen tek şey "zaman aşımı"
    idi ve sunucunun "started server on 0.0.0.0:3000" çıktısı ATILIYORDU. Model
    komutun başarısız olduğunu sandı; oysa komut çalışmıştı, sadece bitmemişti.

    Kısmi çıktı `TimeoutExpired` üzerinde zaten duruyor; kaybedilmesinin bir
    gerekçesi yoktu. Mesaj ayrıca ne yapılacağını söyler (RULES: hata mesajı
    eyleme dönüştürülebilir olur) — en önemlisi aynı komutu tekrar denememeyi,
    çünkü ikinci deneme de aynı süreyi yakar.
    """
    partial = _combine(_as_text(timeout.output), _as_text(timeout.stderr)).strip()
    lead = (
        f"Komut {timeout_s:.0f}s içinde bitmedi ve durduruldu. Sürekli çalışan bir "
        "süreç (dev sunucusu, izleyici) olabilir: böyle bir komut zaten hiç bitmez.\n"
        "Yapılacak: aynı komutu tekrar çalıştırma (ön planda). Uzun ama BİTEN bir iş "
        "(npm install, render, build, export) ise run_shell(command=..., "
        "run_in_background=true) "
        "ile arka planda başlat ve job_status(id, wait_s) ile bekle. Hiç bitmeyen bir "
        "sunucuysa (dev sunucusu) start_preview kullan ya da arka planda başlatıp "
        "doğrulama için biten bir komut (build, test, lint) çalıştır."
    )
    if not partial:
        return f"{lead}\nKomut durdurulana kadar hiç çıktı üretmedi."
    return f"{lead}\n\n[durdurulmadan önceki çıktı]\n{partial}"


def _as_text(value: str | bytes | None) -> str:
    """`TimeoutExpired` çıktısı metin ya da bayt olabilir; ikisini de karşıla."""
    if value is None:
        return ""
    return value if isinstance(value, str) else value.decode("utf-8", errors="replace")


def git(args: ToolArgs, context: ToolContext) -> ToolResult:
    subcommand = require_str(args, "subcommand")
    # require_str boş/yalnızca-boşluk girdiyi zaten reddeder; parts en az bir öğe taşır.
    try:
        # Tırnaklara saygı: `--format="%h %s"` ve `--grep "a b"` `str.split()` ile bozuluyordu.
        parts = shlex.split(subcommand)
    except ValueError as exc:
        return ToolResult.failure(f"git alt komutu ayrıştırılamadı (tırnak hatası?): {exc}")
    if not parts or not git_reads_only(parts):
        allowed = ", ".join(sorted(READONLY_GIT_SUBCOMMANDS))
        return ToolResult.failure(
            f"Yalnızca salt-okunur git komutlarına izin var ({allowed}). "
            "Değiştirici git için run_shell kullan."
        )
    try:
        process = subprocess.run(
            ["git", *parts],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # ikili çıktı UnicodeDecodeError fırlatmasın
            timeout=GIT_TIMEOUT_S,
            cwd=context.root,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ToolResult.failure(f"git çalıştırılamadı: {exc}")

    body = _combine(process.stdout, process.stderr).strip()
    return ToolResult(body or "(çıktı yok)", ok=process.returncode == 0)


def _join(stdout: str, stderr: str) -> str:
    text = stdout or ""
    if stderr:
        text += f"\n[stderr]\n{stderr}"
    return text


def _combine(stdout: str, stderr: str) -> str:
    return truncate_notice(_join(stdout, stderr), output_limit(), ne="komut çıktısı")
