"""Doğrulama kapısını çalıştıran ve sonucu decay'e bağlayan katman.

İki parça:

- `resolve_turn_success` — saf karar: turun "başarılı" sayılıp sayılmayacağını
  turun kendi durumu (model hata verdi mi, adım sınırına dayanıldı mı) ile
  doğrulama sonucundan (varsa) birleştirir. Bu sonuç ders güvenini besler.
- `CommandVerifier` — yapılandırılmış komutları (ruff/mypy/pytest ya da alt kümesi)
  sırayla çalıştıran concrete doğrulayıcı. İlk başarısız komut kapıyı düşürür.

Doğrulama OPT-IN'dir: yapılandırmada komut yoksa doğrulayıcı hiç kurulmaz ve mevcut
davranış birebir korunur.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...config.models import Config
from ...core.constants import SHELL_TIMEOUT_S
from ...core.verification import VerificationResult, Verifier


def resolve_turn_success(
    *, outcome_ok: bool, hit_step_limit: bool, verification: VerificationResult | None
) -> bool:
    """Tur ders güvenini artıracak kadar başarılı mı.

    Temel sinyal: model temiz bitmiş ve adım sınırına dayanılmamış olmalı. Doğrulama
    kapısı devredeyse ayrıca geçmiş olmalı — böylece "test çalıştırmadan bitirme" gibi
    dersler gerçekten uygulanır: kapı kırıksa tur başarısız sayılır ve ders sönmez/güç
    kazanmaz, tersine ilgili ders cezalanır.
    """

    base = outcome_ok and not hit_step_limit
    if verification is None:
        return base
    return base and verification.ok


def build_verifier(config: Config, *, root: Path) -> Verifier | None:
    """Yapılandırmada doğrulama komutu varsa bir doğrulayıcı kur, yoksa None.

    None döndürmek doğrulamanın kapalı olması demektir: mevcut davranış korunur.
    """
    commands = config.runtime.verification_commands
    if not commands:
        return None
    return CommandVerifier(commands, cwd=str(root), timeout_s=SHELL_TIMEOUT_S)


class CommandVerifier:
    """Yapılandırılmış kabuk komutlarını sırayla çalıştıran doğrulayıcı."""

    def __init__(self, commands: tuple[str, ...], *, cwd: str, timeout_s: float) -> None:
        self._commands = commands
        self._cwd = cwd
        self._timeout_s = timeout_s

    async def verify(self) -> VerificationResult:
        for command in self._commands:
            result = await self._run(command)
            if not result.ok:
                return result
        return VerificationResult(ok=True)

    async def _run(self, command: str) -> VerificationResult:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self._cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            return VerificationResult(ok=False, summary=f"komut başlatılamadı: {command} ({exc})")

        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=self._timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            return VerificationResult(ok=False, summary=f"komut zaman aşımına uğradı: {command}")

        if return_code != 0:
            return VerificationResult(
                ok=False, summary=f"komut başarısız (çıkış {return_code}): {command}"
            )
        return VerificationResult(ok=True)
