"""Başlangıç playbook kütüphanesi + kabuk çalıştırıcı.

İlk playbook'lar bilinçli olarak KÜÇÜK ve geri-alınabilir (idempotent) tutulur:
mekanizmayı gerçek ama düşük riskli akışlarla göstermek için. Kütüphane zamanla
eski kayıtlardan çıkan tekrarlayan tamir akışlarıyla büyür.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .model import Playbook, PlaybookStep

#: Çekirdek kütüphane. Sıra önceliktir: ilk eşleşen playbook seçilir.
#: Kalite/test komutlarının hangi tetikleyicilerle eşleştiği.
#
# Komutlar SABİT KODLANMAZ: `verify_discovery` projeyi tanır (pyproject, package.json,
# Cargo.toml, go.mod, Makefile) ve gerçek komutları verir. Eskiden `ruff`/`pytest`
# gömülüydü; bir Node projesinde "lint" yazan kullanıcıda yanlış komut çalışıyor,
# tur boşa gidiyordu. Aynı bilginin iki yerde durması da zamanla ayrışırdı.
_LINT_TRIGGERS = ("biçimlendir", "bicimlendir", "lint", "format", "ruff")
_TEST_TRIGGERS = ("testleri çalıştır", "testleri calistir", "pytest", "testler geçiyor mu", "test")

#: Keşfedilen komutun hangi gruba ait olduğunu anlamak için aranan parçalar.
_TEST_MARKERS = ("pytest", "test", "vitest", "jest")


def build_playbooks(root: Path) -> tuple[Playbook, ...]:
    """Projeyi tanıyıp playbook kütüphanesini üret. Tanınmazsa boş.

    Komut uydurmaktansa playbook hiç sunmamak doğrudur: yanlış komut turu boşa
    harcar ve kullanıcı sebebini anlamaz.
    """
    from ..agent.verify_discovery import discover_commands

    komutlar = discover_commands(root)
    if not komutlar:
        return ()

    test_komutlari = tuple(k for k in komutlar if any(m in k for m in _TEST_MARKERS))
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
