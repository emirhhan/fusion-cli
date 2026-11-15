"""`mcp_tool`, `prompt` ve `agent` kanca türleri (Claude Code hooks başvurusu).

mcp_tool  yapılandırılmış MCP sunucusunun aracı çağrılır; `input` içindeki metinlerde
          `${tool_input.file_path}` gibi yollar kanca girdisinden doldurulur. Aracın metin
          içeriği komut kancasının stdout'u gibi okunur; `isError` ya da bağlı olmayan
          sunucu engellemeyen hatadır.
prompt    kanca girdisi ve istem tek atışta arka plan modeline gider (`$ARGUMENTS` yer
          tutucusu; yoksa girdi sona eklenir, `\\$` düz `$` yazar). Model
          `{"ok": bool, "reason": "...", "impossible": bool}` döndürür.
agent     aynı istem Read/Grep/Glob'lu alt ajana gider (en çok 50 tur); `ok: false`
          prompt kancasının `continueOnBlock: true` davranışıyla işlenir.

`ok: false` olay başına komut kancası çıktısına çevrilir ve ortak karar yolundan geçer
(`core/hooks/decision.py`); böylece birleştirme ve öncelik kuralları aynı kalır.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from ...core.hooks.decision import BLOCK_EXIT_CODE
from ...core.hooks.events import AGENT_HANDLER, HookCommand, HookEvent, HookRun

#: (istem, model, süre sn) → modelin ham yanıt metni.
ModelCall = Callable[[str, str, float], Awaitable[str]]
#: (sunucu, araç, argümanlar) → (metin içeriği, hata mı).
McpCall = Callable[[str, str, Mapping[str, object]], Awaitable[tuple[str, bool]]]

#: Model kancasına verilen yönerge (Claude'un değerlendirici sözleşmesi).
EVALUATOR_SYSTEM = (
    "You are evaluating a hook in Claude Code. Apply the user's rule to the hook input. "
    'Respond with JSON only: {"ok": true} to allow, or {"ok": false, "reason": "..."} '
    'to block. Add "impossible": true when the condition can never be satisfied.'
)
REASON_NO_MCP = "MCP sunucusu bağlı değil: {server}"
REASON_NO_MODEL = "model kancası bu oturumda çalıştırılamıyor (model erişimi yok)"
REASON_BAD_JSON = 'model yanıtı {"ok": …} JSON\'u değil'
_ARGUMENTS = "$ARGUMENTS"
_ESCAPED_DOLLAR = "\0dolar\0"
_PATH = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")
_JSON_OBJECT = re.compile(r"\{.*\}", re.S)
#: `ok: false` gerekçesinin araç hatası olarak modele döndüğü olaylar.
_TOOL_ERROR_EVENTS = frozenset({HookEvent.TASK_CREATED, HookEvent.TASK_COMPLETED})


@dataclass(frozen=True, slots=True)
class HookServices:
    """Kanca oturumunun model/MCP erişimi; verilmeyen erişim engellemeyen hatadır."""

    model_call: ModelCall | None = None
    agent_call: ModelCall | None = None
    mcp_call: McpCall | None = None


def render_prompt(template: str, payload: Mapping[str, object]) -> str:
    """`$ARGUMENTS` → girdi JSON'u; yer tutucu yoksa girdi sona eklenir."""
    body = json.dumps(payload, ensure_ascii=False, default=str)
    text = template.replace("\\$", _ESCAPED_DOLLAR)
    text = text.replace(_ARGUMENTS, body) if _ARGUMENTS in text else f"{text}\n\n{body}"
    return text.replace(_ESCAPED_DOLLAR, "$")


def substitute_paths(value: object, payload: Mapping[str, object]) -> object:
    """`input` içindeki metinlerde `${a.b}` yolunu kanca girdisinden doldur."""
    if isinstance(value, str):
        whole = _PATH.fullmatch(value)
        if whole is not None:
            found = _lookup(payload, whole.group(1))
            return value if found is None else found
        return _PATH.sub(lambda match: _as_text(_lookup(payload, match.group(1)), match), value)
    if isinstance(value, Mapping):
        return {str(key): substitute_paths(item, payload) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute_paths(item, payload) for item in value]
    return value


def _lookup(payload: Mapping[str, object], path: str) -> object | None:
    current: object = payload
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _as_text(found: object | None, match: re.Match[str]) -> str:
    if found is None:
        return match.group(0)
    return found if isinstance(found, str) else json.dumps(found, ensure_ascii=False)


async def run_mcp_hook(
    command: HookCommand, payload: Mapping[str, object], services: HookServices | None
) -> HookRun:
    """MCP aracını çağır; metin içeriği stdout olur (çıkış 0)."""
    caller = services.mcp_call if services is not None else None
    if caller is None:
        return HookRun(command, None, error=REASON_NO_MCP.format(server=command.server))
    raw = json.loads(command.tool_input_json) if command.tool_input_json else {}
    arguments = substitute_paths(raw, payload)
    args = arguments if isinstance(arguments, Mapping) else {}
    try:
        async with asyncio.timeout(command.timeout_s):
            text, is_error = await caller(command.server, command.tool, args)
    except TimeoutError:
        return HookRun(command, None, timed_out=True)
    except LookupError:
        return HookRun(command, None, error=REASON_NO_MCP.format(server=command.server))
    except (RuntimeError, OSError) as error:
        return HookRun(command, None, error=str(error) or type(error).__name__)
    if is_error:
        return HookRun(command, 1, "", text or "MCP aracı hata döndürdü")
    return HookRun(command, 0, text, "")


async def run_model_hook(
    command: HookCommand,
    event: HookEvent | None,
    payload: Mapping[str, object],
    services: HookServices | None,
) -> HookRun:
    """İstemi modele (ya da alt ajana) ver; `{ok, reason}` kararını kanca çıktısına çevir."""
    is_agent = command.handler == AGENT_HANDLER
    caller = None
    if services is not None:
        caller = services.agent_call if is_agent else services.model_call
    if caller is None or event is None:
        return HookRun(command, None, error=REASON_NO_MODEL)
    prompt = render_prompt(command.command, payload)
    try:
        async with asyncio.timeout(command.timeout_s):
            answer = await caller(prompt, command.model, command.timeout_s)
    except TimeoutError:
        return HookRun(command, None, timed_out=True)
    except (RuntimeError, OSError) as error:
        return HookRun(command, None, error=str(error) or type(error).__name__)
    decision = parse_decision(answer)
    if decision is None:
        return HookRun(command, 1, "", REASON_BAD_JSON)
    ok, reason, impossible = decision
    if ok:
        return HookRun(command, 0, "", "")
    continue_on_block = is_agent or command.continue_on_block
    return blocked_run(command, event, reason, continue_on_block, impossible and not is_agent)


def parse_decision(text: str) -> tuple[bool, str, bool] | None:
    """Model yanıtındaki ilk JSON nesnesi: (ok, gerekçe, impossible)."""
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
        return None
    return data["ok"], str(data.get("reason") or "").strip(), data.get("impossible") is True


def blocked_run(
    command: HookCommand, event: HookEvent, reason: str, continue_on_block: bool, impossible: bool
) -> HookRun:
    """`ok: false` → olayın komut kancası karşılığı (Claude "Response schema" tablosu)."""
    reason = reason or "kanca koşulu sağlanmadı"
    if event is HookEvent.PERMISSION_REQUEST:
        # Claude: `ok: false` izin isteğinde etkisizdir (karar için komut kancası gerekir).
        return HookRun(command, 0)
    if event in (HookEvent.STOP, HookEvent.SUBAGENT_STOP):
        return HookRun(command, 0) if impossible else _json(command, _block(reason))
    if event in _TOOL_ERROR_EVENTS:
        return HookRun(command, BLOCK_EXIT_CODE, "", reason)
    if event is HookEvent.PRE_TOOL_USE:
        deny = {
            "hookSpecificOutput": {
                "hookEventName": event.value,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        return _json(command, deny if continue_on_block else {**deny, **_halt(reason)})
    if event is HookEvent.POST_TOOL_USE:
        return _json(command, _block(reason) if continue_on_block else _halt(reason))
    if event is HookEvent.TEAMMATE_IDLE:
        if continue_on_block:
            return HookRun(command, BLOCK_EXIT_CODE, "", reason)
        return _json(command, _halt(reason))
    # UserPromptSubmit/PostToolBatch (turu bitirir), PostToolUseFailure (araç hatası).
    return _json(command, _block(reason))


def _block(reason: str) -> dict[str, object]:
    return {"decision": "block", "reason": reason}


def _halt(reason: str) -> dict[str, object]:
    return {"continue": False, "stopReason": reason}


def _json(command: HookCommand, data: Mapping[str, object]) -> HookRun:
    return HookRun(command, 0, json.dumps(data, ensure_ascii=False), "")
