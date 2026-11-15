"""`PreModelSwitch` / `PostModelSwitch` kancaları (#90): `/model` oturum modelini değiştirince.

Claude: eşleştirici hedef modelin kanonik adıdır (Fusion'da `sağlayıcı/model` ve yalın
`model`). PreModelSwitch çıkış 2, `decision: "block"` ya da `permissionDecision: "deny"`
ile değişikliği iptal eder; `ask` yalnız etkileşimli `/model`'de sorulabilir, Fusion'da
(soru kartı yok) ret sayılır — Claude'un öteki yüzeylerdeki kuralı. `systemMessage` her
durumda kullanıcıya gösterilir. PostModelSwitch engelleyemez; düz stdout ve
`additionalContext` sonraki istekle modele gider.

`/model` işleyicisi eşzamanlıdır: kanca ayrı iş parçacığında kendi olay döngüsünde koşar
(model değişikliği kanca bitene dek bekler, Claude'daki gibi).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Callable, Coroutine
from dataclasses import dataclass

from ...core.hooks.events import HookEvent, HookVerdict
from ..hooks.session import HookSession

COMMAND_SOURCE = "command"


@dataclass(frozen=True, slots=True)
class SwitchGate:
    """PreModelSwitch sonucu: ret gerekçesi (yoksa izin) ve kullanıcıya gösterilecek satırlar."""

    refused: str | None = None
    messages: tuple[str, ...] = ()


def canonical(model: str) -> str:
    """`anthropic/claude-opus-5[1m]` → `claude-opus-5` (sağlayıcı öneki ve `[1m]` atılır)."""
    return model.split("/")[-1].removesuffix("[1m]")


def _fields(
    from_model: str, to_model: str, requested: str | None, source: str
) -> dict[str, object]:
    return {
        "from_model": from_model,
        "to_model": to_model,
        "requested_model": requested,
        "source": source,
        # Fusion önbellek maliyetini ölçmez: bilinmeyen fiyat Claude'daki gibi `default`.
        "context_tokens": 0,
        "prompt_cache_warm": False,
        "cache_ttl": "5m",
        "estimated_cache_write_usd": 0.0,
        "pricing": "default",
    }


def _run_blocking(work: Callable[[], Coroutine[object, object, HookVerdict]]) -> HookVerdict:
    """Eşzamanlı koddan kancayı çalıştır (çalışan olay döngüsünü bölmeden)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(work())).result()


def pre_model_switch(
    session: HookSession | None,
    from_model: str,
    to_model: str,
    *,
    requested: str | None,
    source: str = COMMAND_SOURCE,
) -> SwitchGate:
    if session is None or from_model == to_model or not session.has(HookEvent.PRE_MODEL_SWITCH):
        return SwitchGate()
    fields = _fields(from_model, to_model, requested, source)
    subjects = (canonical(to_model), to_model)
    verdict = _run_blocking(
        lambda: session.emit(HookEvent.PRE_MODEL_SWITCH, subjects=subjects, fields=fields)
    )
    shown = (*verdict.system_messages, *verdict.errors)
    if verdict.blocked or verdict.permission in ("deny", "ask"):
        reason = verdict.reason or verdict.ask_reason or "kanca model değişikliğini engelledi"
        return SwitchGate(refused=f"PreModelSwitch hook: {reason}", messages=shown)
    return SwitchGate(messages=shown)


def post_model_switch(
    session: HookSession | None,
    from_model: str,
    to_model: str,
    *,
    requested: str | None,
    source: str = COMMAND_SOURCE,
) -> tuple[str, ...]:
    """Model değişti: bağlam sonraki tura (`rewake_notes`); kullanıcı satırları döner."""
    if session is None or from_model == to_model or not session.has(HookEvent.POST_MODEL_SWITCH):
        return ()
    fields = _fields(from_model, to_model, requested, source)
    subjects = (canonical(to_model), to_model)
    verdict = _run_blocking(
        lambda: session.emit(HookEvent.POST_MODEL_SWITCH, subjects=subjects, fields=fields)
    )
    if verdict.context_text:
        session.rewake_notes.append(
            f"{HookEvent.POST_MODEL_SWITCH.value} hook additional context: {verdict.context_text}"
        )
    return (*verdict.system_messages, *verdict.errors)
