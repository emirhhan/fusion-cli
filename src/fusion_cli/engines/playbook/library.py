"""Başlangıç playbook kütüphanesi + kabuk çalıştırıcı.

İlk playbook'lar bilinçli olarak KÜÇÜK ve geri-alınabilir (idempotent) tutulur:
mekanizmayı gerçek ama düşük riskli akışlarla göstermek için. Kütüphane zamanla
eski kayıtlardan çıkan tekrarlayan tamir akışlarıyla büyür.
"""

from __future__ import annotations

import asyncio

from .model import Playbook, PlaybookStep

#: Çekirdek kütüphane. Sıra önceliktir: ilk eşleşen playbook seçilir.
PLAYBOOKS: tuple[Playbook, ...] = (
    Playbook(
        id="bicimlendir-ve-lint-duzelt",
        description="Kodu biçimlendir ve lint hatalarını otomatik düzelt, sonra temiz mi doğrula.",
        triggers=("biçimlendir", "bicimlendir", "lint", "format", "ruff"),
        steps=(
            PlaybookStep("Kodu biçimlendir", "ruff format ."),
            PlaybookStep("Lint hatalarını düzelt", "ruff check --fix ."),
        ),
        checks=("ruff check .",),
    ),
    Playbook(
        id="testleri-calistir",
        description="Depodaki testleri çalıştır ve hepsinin geçtiğini doğrula.",
        triggers=("testleri çalıştır", "testleri calistir", "pytest", "testler geçiyor mu"),
        steps=(PlaybookStep("Testleri çalıştır", "pytest -q"),),
        checks=("pytest -q",),
    ),
)


class ShellStepRunner:
    """Playbook adımlarını gerçek kabukta çalıştıran koşucu (çıkış kodunu döndürür)."""

    def __init__(self, *, cwd: str, timeout_s: float) -> None:
        self._cwd = cwd
        self._timeout_s = timeout_s

    async def run(self, command: str) -> int:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self._cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return 1
        try:
            return await asyncio.wait_for(process.wait(), timeout=self._timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            return 1
