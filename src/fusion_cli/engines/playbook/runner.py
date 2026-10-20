"""Playbook çalıştırıcı — adımları sırayla koşturur, başarısızlıkta geri alır.

Adımların yürütülmesi bir `StepRunner` protokolünün arkasındadır: gerçek çalıştırma
kabuk komutudur ama test sahte bir koşucuyla yan etkisiz doğrulanabilir.

Geri alma sözleşmesi: bir adım ya da `checks` başarısız olursa, o ana dek ÇALIŞTIRILMIŞ
adımlar TERS sırada geri alınır (yalnızca geri-alma komutu tanımlı olanlar).
"""

from __future__ import annotations

from typing import Protocol

from .model import Playbook, PlaybookResult, PlaybookStep


class StepRunner(Protocol):
    """Bir kabuk komutu çalıştırıp çıkış kodunu döndüren taraf."""

    async def run(self, command: str) -> int: ...


async def run_playbook(playbook: Playbook, runner: StepRunner) -> PlaybookResult:
    """Playbook'u çalıştır. Adım ya da doğrulama kırılırsa geri al ve başarısız dön."""

    executed: list[PlaybookStep] = []
    ran_descriptions: list[str] = []

    for step in playbook.steps:
        code = await runner.run(step.command)
        executed.append(step)
        ran_descriptions.append(step.description)
        if code != 0:
            rolled_back = await _rollback(executed, runner)
            return PlaybookResult(
                ok=False,
                ran_steps=tuple(ran_descriptions),
                summary=f"adım başarısız (çıkış {code}): {step.description}",
                rolled_back=rolled_back,
            )

    failed_check = await _first_failing_check(playbook.checks, runner)
    if failed_check is not None:
        rolled_back = await _rollback(executed, runner)
        return PlaybookResult(
            ok=False,
            ran_steps=tuple(ran_descriptions),
            summary=f"doğrulama başarısız: {failed_check}",
            rolled_back=rolled_back,
        )

    return PlaybookResult(
        ok=True,
        ran_steps=tuple(ran_descriptions),
        summary=f"playbook tamamlandı: {playbook.id}",
    )


async def _first_failing_check(checks: tuple[str, ...], runner: StepRunner) -> str | None:
    for check in checks:
        if await runner.run(check) != 0:
            return check
    return None


async def _rollback(executed: list[PlaybookStep], runner: StepRunner) -> bool:
    """Çalıştırılmış adımları ters sırada geri al. En az bir geri-alma çalıştıysa True."""

    rolled_back = False
    for step in reversed(executed):
        if step.rollback:
            await runner.run(step.rollback)
            rolled_back = True
    return rolled_back
