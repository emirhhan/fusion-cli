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
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ...core.constants import SHELL_TIMEOUT_S

#: Kancanın çalıştığı dosya araçları.
EDIT_TOOLS = frozenset({"write_file", "edit_file", "multi_edit"})
#: Kanca çıktısından modele gösterilecek en fazla karakter.
HOOK_OUTPUT_CHARS = 1_500


async def run_post_edit_hooks(commands: Sequence[str], path: Path, root: Path) -> str | None:
    """Kancaları sırayla çalıştır; hepsi başarılıysa None, değilse modele not."""
    notes: list[str] = []
    for template in commands:
        command = template.replace("{path}", shlex.quote(str(path)))
        result = await asyncio.to_thread(_run, command, root)
        if result is not None:
            notes.append(f"`{command}` → {result}")
    if not notes:
        return None
    return "DÜZENLEME KANCASI BAŞARISIZ (kullanıcının post_edit_commands ayarı):\n" + "\n".join(
        notes
    )


def _run(command: str, root: Path) -> str | None:
    try:
        process = subprocess.run(
            command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return f"{SHELL_TIMEOUT_S:g} sn'de bitmedi"
    except OSError as error:
        return f"çalıştırılamadı: {error}"
    if process.returncode == 0:
        return None
    output = (process.stdout + process.stderr).strip()[-HOOK_OUTPUT_CHARS:]
    return f"çıkış kodu {process.returncode}\n{output}"
