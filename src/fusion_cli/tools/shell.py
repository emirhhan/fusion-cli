"""Kabuk ve git araçları.

`git` bilinçli olarak SALT-OKUNURDUR: yalnızca beyaz listedeki alt komutlar çalışır
ve onay gerektirmez. Durum/diff/log okumak için her seferinde onay istemek kullanıcıyı
yorar; commit/push gibi değiştirici git işlemleri `run_shell` üzerinden geçer ve
oradaki onay + tehlike kontrolüne tabi olur.
"""

from __future__ import annotations

import subprocess

from ..core.constants import (
    GIT_TIMEOUT_S,
    MAX_OUTPUT_CHARS,
    SHELL_TIMEOUT_S,
    truncate_notice,
)
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .command_policy import READONLY_GIT_SUBCOMMANDS

__all__ = ["READONLY_GIT_SUBCOMMANDS", "git", "run_shell"]


def run_shell(args: ToolArgs, context: ToolContext) -> ToolResult:
    command = require_str(args, "command")
    try:
        # shell=True bilinçli: kullanıcı boru/yönlendirme içeren komut yazabilmeli.
        # Komut buraya gelmeden önce tehlike kontrolünden ve onay akışından geçer.
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_S,
            cwd=context.root,
        )
    except subprocess.TimeoutExpired as timeout:
        return ToolResult.failure(_timeout_message(timeout))
    except OSError as exc:
        return ToolResult.failure(f"Komut çalıştırılamadı: {exc}")

    body = _combine(process.stdout, process.stderr)
    text = f"(çıkış kodu {process.returncode})\n{body}".strip()
    return ToolResult(text, ok=process.returncode == 0)


def _timeout_message(timeout: subprocess.TimeoutExpired) -> str:
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
        f"Komut {SHELL_TIMEOUT_S:.0f}s içinde bitmedi ve durduruldu. Sürekli çalışan bir "
        "süreç (dev sunucusu, izleyici) olabilir: böyle bir komut zaten hiç bitmez.\n"
        "Yapılacak: aynı komutu tekrar çalıştırma. Çıktıya bakıp sürecin başlayıp "
        "başlamadığını anla; sürekli çalışması gerekiyorsa kullanıcıdan onu kendi "
        "terminalinde başlatmasını iste, doğrulama için biten bir komut (build, test, "
        "lint) kullan."
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
    parts = subcommand.split()
    if parts[0] not in READONLY_GIT_SUBCOMMANDS:
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
            timeout=GIT_TIMEOUT_S,
            cwd=context.root,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ToolResult.failure(f"git çalıştırılamadı: {exc}")

    body = _combine(process.stdout, process.stderr).strip()
    return ToolResult(body or "(çıktı yok)", ok=process.returncode == 0)


def _combine(stdout: str, stderr: str) -> str:
    text = stdout or ""
    if stderr:
        text += f"\n[stderr]\n{stderr}"
    return truncate_notice(text, MAX_OUTPUT_CHARS, ne="komut çıktısı")
