"""Başlangıç playbook kütüphanesi + kabuk çalıştırıcı.

İlk playbook'lar bilinçli olarak KÜÇÜK ve geri-alınabilir (idempotent) tutulur:
mekanizmayı gerçek ama düşük riskli akışlarla göstermek için. Kütüphane zamanla
eski kayıtlardan çıkan tekrarlayan tamir akışlarıyla büyür.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from ...core.errors import CleanupFailedError
from ...core.process_control import (
    process_group_options,
    terminate_async_process_tree,
    wait_for_shell_exit,
)
from .model import Playbook, PlaybookStep

logger = logging.getLogger(__name__)

#: Çekirdek kütüphane. Sıra önceliktir: ilk eşleşen playbook seçilir.
#: Kalite/test komutlarının hangi tetikleyicilerle eşleştiği.
#
# Komutlar SABİT KODLANMAZ: `verify_discovery` projeyi tanır (pyproject, package.json,
# Cargo.toml, go.mod, Makefile) ve gerçek komutları verir. Eskiden `ruff`/`pytest`
# gömülüydü; bir Node projesinde "lint" yazan kullanıcıda yanlış komut çalışıyor,
# tur boşa gidiyordu. Aynı bilginin iki yerde durması da zamanla ayrışırdı.
_LINT_TRIGGERS = ("biçimlendir", "bicimlendir", "lint", "format", "ruff")
_TEST_TRIGGERS = ("testleri çalıştır", "testleri calistir", "pytest", "testler geçiyor mu", "test")

#: Keşfedilen komutun TEST komutu olduğunu gösteren sözcükler. Alt dizge değil TAM sözcük
#: aranır: Ölçüldü (30 Ekim) `ruff check src tests` komutu "test" içerdiği için test grubuna
#: düşüyor, lint playbook'u eksik kalıyordu (E1-28). `tests` dizini, `src/test` yolu ve
#: `contest` gibi sözcükler eşleşmez; `npm run test:unit`, `go test ./...`, `pytest -q` eşleşir.
_TEST_COMMAND = re.compile(r"(?<![\w/.\-])(?:pytest|vitest|jest|test)(?![\w/\-])")


def build_playbooks(root: Path) -> tuple[Playbook, ...]:
    """Projeyi tanıyıp playbook kütüphanesini üret. Tanınmazsa boş.

    Komut uydurmaktansa playbook hiç sunmamak doğrudur: yanlış komut turu boşa
    harcar ve kullanıcı sebebini anlamaz.
    """
    from ..agent.verify_discovery import discover_commands

    komutlar = discover_commands(root)
    if not komutlar:
        return ()

    test_komutlari = tuple(k for k in komutlar if _TEST_COMMAND.search(k))
    lint_komutlari = tuple(k for k in komutlar if k not in test_komutlari)

    kitaplar: list[Playbook] = []
    if lint_komutlari:
        kitaplar.append(
            Playbook(
                id="bicimlendir-ve-lint-duzelt",
                description="Kodu denetle ve lint hatalarını düzelt, sonra temiz mi doğrula.",
                triggers=_LINT_TRIGGERS,
                steps=tuple(PlaybookStep(f"Çalıştır: {k}", k) for k in lint_komutlari),
                checks=lint_komutlari,
            )
        )
    if test_komutlari:
        kitaplar.append(
            Playbook(
                id="testleri-calistir",
                description="Projedeki testleri çalıştır ve geçtiklerini doğrula.",
                triggers=_TEST_TRIGGERS,
                steps=tuple(PlaybookStep(f"Çalıştır: {k}", k) for k in test_komutlari),
                checks=test_komutlari,
            )
        )
    return tuple(kitaplar)


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
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                **process_group_options(),
            )
        except OSError:
            return 1
        # Her çıkış yolunda (normal, zaman aşımı, iptal) süreç GRUBU temizlenir.
        # Ölçüldü (29 Ekim): `process.kill()` yalnız kabuğu öldürüyordu; `npm test`
        # altındaki torunlar yetim kalıyordu (E1-27).
        try:
            return await asyncio.wait_for(wait_for_shell_exit(process), timeout=self._timeout_s)
        except TimeoutError:
            return 1
        finally:
            try:
                await terminate_async_process_tree(process)
            except CleanupFailedError:
                logger.warning("playbook adımının süreç ağacı temizlenemedi: %s", command)
