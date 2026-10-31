"""Headless (betik) koşu yardımcıları — `fusion agent`'ın Claude Code `-p` paritesi (P-026).

Komut fonksiyonu ince kalsın diye bayrakların yorumu buradadır: stdin görevi, çıktı
biçimi, araç izin/yasak listeleri, ajan tanımı, JSON şeması ve JSON-Lines onay kanalı.

Ölçüldü (31 Ekim): `fusion agent` görevi yalnız argüman olarak alıyor, `--json` satırları
belgelenmiş bir olay şemasına uymuyor, etkileşimsiz oturumda onay istemi
`UNAVAILABLE`'a düşüyordu; betik ne izin isteğini görüyor ne cevap verebiliyordu.

Onay kanalı protokolü (`--permission-channel stdin`, JSON-Lines; bkz. docs/HEADLESS.md):

    stdout → {"event": "ApprovalRequested", "istek_id": "1", "arac": "run_shell", ...}
    stdin  ← {"istek_id": "1", "karar": "onayla" | "oturum" | "reddet"}
    stdout → {"event": "QuestionAsked", "istek_id": "2", "soru": "...", "secenekler": [...]}
    stdin  ← {"istek_id": "2", "cevap": "..."}

Eşleşmeyen kimlik, bozuk satır ya da EOF insan reddi DEĞİLDİR: `UNAVAILABLE` döner ve
tur sürer (bkz. `engines/agent/denial.py`).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import TextIO

from .. import __version__
from ..config.models import Config
from ..core.json_schema import validate_instance
from ..core.redaction import redact
from ..engines.agent.approval import ApprovalAnswer, ApprovalMode, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..engines.agent.team import GENERIC_PERSONA, Persona, resolve_persona
from ..observability.cost import CostTracker
from ..tools.capabilities import CapabilityRegistry
from ..ui import messages


class OutputFormat(Enum):
    """`--output-format` değerleri (Claude Code ile aynı adlar)."""

    TEXT = "text"
    #: Tek satır: nihai sonuç nesnesi (`{"type": "result", ...}`).
    JSON = "json"
    #: Her olay bir satır (`JsonRenderer`); ilk satır `SystemInit`.
    STREAM_JSON = "stream-json"


class PermissionChannel(Enum):
    """`--permission-channel` değerleri."""

    STDIN = "stdin"


#: Onay kanalında kabul edilen kararlar → `ApprovalAnswer`.
_DECISIONS: Mapping[str, ApprovalAnswer] = {
    "onayla": ApprovalAnswer.ONCE,
    "once": ApprovalAnswer.ONCE,
    "allow": ApprovalAnswer.ONCE,
    "oturum": ApprovalAnswer.SESSION,
    "session": ApprovalAnswer.SESSION,
    "reddet": ApprovalAnswer.DENY,
    "deny": ApprovalAnswer.DENY,
}

#: Nihai cevaptan JSON'u ayıklarken kod çitini söken desen.
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_output_format(raw: str) -> OutputFormat:
    """Biçim adını çöz; bilinmiyorsa `ValueError` (komut `BadParameter`e çevirir)."""
    try:
        return OutputFormat(raw.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in OutputFormat)
        raise ValueError(messages.HEADLESS_UNKNOWN_FORMAT.format(given=raw, valid=valid)) from None


def parse_permission_channel(raw: str | None) -> PermissionChannel | None:
    if raw is None or not raw.strip():
        return None
    try:
        return PermissionChannel(raw.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in PermissionChannel)
        raise ValueError(messages.HEADLESS_UNKNOWN_CHANNEL.format(given=raw, valid=valid)) from None


def read_task(task: str, stdin: TextIO, *, is_tty: bool) -> str:
    """`-` ya da boş görev boru hattında stdin'den okunur (Codex `codex exec -`)."""
    text = task.strip()
    if text == "-" or (not text and not is_tty):
        return stdin.read().strip()
    return "" if text == "-" else text


def parse_tool_list(raw: Iterable[str] | None) -> frozenset[str] | None:
    """`--allowed-tools a,b --allowed-tools c` → {a, b, c}; hiç verilmediyse None."""
    if raw is None:
        return None
    names = {name.strip() for chunk in raw for name in chunk.split(",") if name.strip()}
    return frozenset(names)


def apply_limits(
    config: Config,
    *,
    max_turns: int | None,
    max_budget_usd: float | None,
    bare: bool,
) -> Config:
    """Bayrakları yapılandırmaya işle; `--bare` MCP/bağlayıcı/talimat yüklemesini kapatır."""
    runtime = config.runtime
    if max_turns is not None:
        runtime = replace(runtime, agent_max_steps=max_turns)
    if max_budget_usd is not None:
        runtime = replace(runtime, agent_max_cost_usd=max_budget_usd)
    if bare:
        runtime = replace(runtime, project_instructions=False)
        config = replace(config, mcp_servers=(), hosted_connectors=())
    return replace(config, runtime=runtime)


def load_schema(path: Path) -> dict[str, object]:
    """Şema dosyasını oku; okunamıyorsa Türkçe hata (`ValueError`)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            messages.HEADLESS_SCHEMA_UNREADABLE.format(path=path, error=error)
        ) from None
    if not isinstance(data, dict):
        raise ValueError(
            messages.HEADLESS_SCHEMA_UNREADABLE.format(path=path, error="kök bir nesne olmalı")
        )
    return data


def schema_instruction(schema: Mapping[str, object]) -> str:
    """Modele giden sistem eki: nihai cevap bu şemaya uyan tek JSON nesnesi olsun."""
    return messages.HEADLESS_SCHEMA_INSTRUCTION.format(
        schema=json.dumps(schema, ensure_ascii=False)
    )


@dataclass(frozen=True, slots=True)
class StructuredResult:
    """Nihai cevabın şemaya göre ayrıştırılmış hâli."""

    value: object | None
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def structured_result(final_text: str, schema: Mapping[str, object]) -> StructuredResult:
    """Cevaptan JSON'u ayıkla (kod çiti söker) ve şemaya göre denetle."""
    text = final_text.strip()
    fenced = _FENCE.search(text)
    if fenced is not None:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return StructuredResult(None, (messages.HEADLESS_STRUCTURED_NOT_JSON.format(error=error),))
    errors = validate_instance(value, schema)
    return StructuredResult(value, tuple(errors))


def resolve_agent(name: str, *, home: Path, root: Path) -> Persona:
    """`--agent <ad>` tanımını (.claude/agents/<ad>.md) kişiliğe çevir; yoksa `ValueError`."""
    library = CapabilityRegistry(home, root)
    persona = resolve_persona(library, name)
    if persona is GENERIC_PERSONA:
        available = (
            ", ".join(item.name for item in library.agents()) or messages.HEADLESS_AGENT_NONE
        )
        raise ValueError(messages.HEADLESS_AGENT_NOT_FOUND.format(name=name, available=available))
    return persona


def system_init_line(config: Config, mode: ApprovalMode, *, root: Path, channel: str | None) -> str:
    """stream-json'un ilk satırı (Claude Code `system/init` karşılığı)."""
    return json.dumps(
        {
            "event": "SystemInit",
            "surum": __version__,
            "model": config.agent.model,
            "kip": mode.value,
            "cwd": str(root),
            "izin_kanali": channel,
            "mcp_sunuculari": [server.name for server in config.mcp_servers],
        },
        ensure_ascii=False,
    )


def result_object(
    *,
    final_text: str,
    ok: bool,
    budget_stopped: bool,
    stop_reason: str | None,
    model_calls: int,
    cost: CostTracker,
    structured: StructuredResult | None,
) -> dict[str, object]:
    """`--output-format json` tek satırlık sonuç nesnesi."""
    if ok and (structured is None or structured.ok):
        durum = "completed"
    elif budget_stopped:
        durum = "budget"
    else:
        durum = "failed"
    total = cost.total
    return {
        "type": "result",
        "ok": durum == "completed",
        "durum": durum,
        "sonuc": redact(final_text),
        "yapisal": structured.value if structured is not None else None,
        "yapisal_hatalar": list(structured.errors) if structured is not None else [],
        "durma_nedeni": stop_reason,
        "model_cagri": model_calls,
        "kullanim": {
            "girdi_token": total.prompt_tokens,
            "cikti_token": total.completion_tokens,
            "maliyet_usd": round(total.cost_usd, 6),
            "maliyet_tam": cost.cost_complete,
            "cagri": cost.calls,
        },
    }


class JsonLinesPrompter:
    """Onay ve soruları JSON-Lines ile dış sürece soran arayüz (`Prompter` + `UserAsker`)."""

    def __init__(self, *, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._counter = 0

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer:
        istek_id = self._next_id()
        self._emit(
            {
                "event": "ApprovalRequested",
                "istek_id": istek_id,
                "arac": request.tool.name,
                "args": request.args,
                "tehlike": request.danger,
                "not": request.note,
                "etki": request.effect.value,
            }
        )
        reply = self._read(istek_id)
        karar = str(reply.get("karar", "")).strip().lower() if reply is not None else ""
        answer = _DECISIONS.get(karar, ApprovalAnswer.UNAVAILABLE)
        self._emit({"event": "ApprovalResolved", "istek_id": istek_id, "karar": answer.value})
        return answer

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        istek_id = self._next_id()
        self._emit(
            {
                "event": "QuestionAsked",
                "istek_id": istek_id,
                "soru": question,
                "secenekler": [
                    {"etiket": option.label, "aciklama": option.description} for option in options
                ],
                "onerilen": recommended,
            }
        )
        reply = self._read(istek_id)
        cevap = str(reply.get("cevap", "")).strip() if reply is not None else ""
        return cevap or messages.NO_ANSWER_AVAILABLE

    # ----------------------------------------------------------------------- #

    def _next_id(self) -> str:
        self._counter += 1
        return str(self._counter)

    def _emit(self, payload: Mapping[str, object]) -> None:
        line = json.dumps(payload, ensure_ascii=False, default=str)
        self._stdout.write(redact(line) + "\n")
        self._stdout.flush()

    def _read(self, istek_id: str) -> Mapping[str, object] | None:
        """Beklenen kimliğe ait satırı oku; EOF/bozuk satır/yanlış kimlik → None."""
        try:
            line = self._stdin.readline()
        except (OSError, ValueError):
            return None
        if not line:
            return None
        try:
            reply = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(reply, dict) or str(reply.get("istek_id", "")) != istek_id:
            return None
        return reply
