"""Düzenleme sonrası kancalar — dosya değişince kullanıcının komutları çalışır.

Kullanıcı `runtime.post_edit_commands` ile biçimlendirici/denetleyici tanımlar
(ör. `npx prettier --write {path}`, `ruff format {path}`). Ajan bir dosyayı
BAŞARIYLA değiştirince her komut o dosya için çalışır; yol `shlex.quote` ile
yerleştirilir. Başarısız kanca turu durdurmaz: çıktısı araç sonucuna eklenir,
model hatayı görüp düzeltir.

Komutlar kullanıcının kendi yapılandırmasından gelir (model üretmez); bu yüzden
onay akışından geçmez — Claude Code'un PostToolUse kancalarıyla aynı güven düzeyi.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shlex
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ...core.constants import SHELL_TIMEOUT_S

#: Kancanın çalıştığı dosya araçları.
EDIT_TOOLS = frozenset({"write_file", "edit_file", "multi_edit"})
#: Kanca çıktısından modele gösterilecek en fazla karakter.
HOOK_OUTPUT_CHARS = 1_500


async def run_post_edit_hooks(commands: Sequence[str], path: Path, root: Path) -> str | None:
    """Kancaları sırayla çalıştır; hepsi başarılıysa ve dosya değişmediyse None, değilse modele not.

    Ölçüldü (30 Ekim, A1-40): biçimlendirici dosyayı yeniden yazınca model bunu
    bilmiyordu ve sonraki `edit_file`'ın `old_string`'i eşleşmiyordu ("bulunamadı"
    döngüsü). Başarılı ama dosyayı DEĞİŞTİREN kanca artık modele bildirilir.
    """
    notes: list[str] = []
    before = await asyncio.to_thread(_digest, path)
    for template in commands:
        command = template.replace("{path}", shlex.quote(str(path)))
        result = await asyncio.to_thread(_run, command, root)
        if result is not None:
            notes.append(f"`{command}` → {result}")
    after = await asyncio.to_thread(_digest, path)
    if not notes:
        if before is not None and after is not None and before != after:
            return (
                "DÜZENLEME KANCASI DOSYAYI YENİDEN YAZDI (biçimlendirici): içerik senin "
                "yazdığından farklı olabilir. Bu dosyayı yeniden düzenlemeden ÖNCE "
                "read_file ile güncel halini oku."
            )
        return None
    return "DÜZENLEME KANCASI BAŞARISIZ (kullanıcının post_edit_commands ayarı):\n" + "\n".join(
        notes
    )


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _run(command: str, root: Path) -> str | None:
    # Kendi süreç grubu: zaman aşımında `shell=True` yalnız kabuğu öldürürdü, altındaki
    # `npx prettier` gibi çocuklar yetim kalırdı (A1-40b).
    posix = os.name == "posix"
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=posix,
        )
    except OSError as error:
        return f"çalıştırılamadı: {error}"
    try:
        stdout, stderr = process.communicate(timeout=SHELL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            if posix:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        process.communicate()
        return f"{SHELL_TIMEOUT_S:g} sn'de bitmedi"
    if process.returncode == 0:
        return None
    output = (stdout + stderr).strip()[-HOOK_OUTPUT_CHARS:]
    return f"çıkış kodu {process.returncode}\n{output}"
