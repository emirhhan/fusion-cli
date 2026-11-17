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

Eşleşmeyen kimlik, bozuk satır, EOF ya da zaman aşımı insan reddi DEĞİLDİR: `UNAVAILABLE`
döner ve tur sürer (bkz. `engines/agent/denial.py`). Zaman aşımına uğramış isteğe geç gelen
cevap atlanır; sonraki isteğe sayılmaz.

Ölçüldü (31 Ekim, inceleme): okuma olay döngüsü içinde bloklayan `readline` idi; cevap
gelmezse tur ve tüm zamanlayıcılar donuyordu. `--output-format json`'da olay satırları
tek satırlık sonuçla aynı stdout'a karışıyordu. Okuma artık daemon iş parçacığında
(süreç çıkışını bekletmez), olaylar json/text biçiminde stderr'e gider.
"""

from __future__ import annotations

import asyncio
import json
import queue
import re
import sys
import threading
import time
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
from ..tools.capabilities import CLAUDE_TOOL_MAP, Capability, CapabilityRegistry
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

#: Onay/soru cevabı için varsayılan bekleme (saniye); `--permission-timeout` ile değişir.
DEFAULT_PERMISSION_TIMEOUT = 300.0
#: Okuyucu kuyruğunu yoklama aralığı (saniye); onay gecikmesi için yeterince küçük.
_POLL_INTERVAL = 0.02
#: Okuyucu iş parçacığının EOF işareti.
_EOF = None

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


#: Claude Code MCP araç öneki (`mcp__github__get_issue`); Fusion'da `github__get_issue`.
_CLAUDE_MCP_PREFIX = "mcp__"


def map_claude_tool_names(names: frozenset[str]) -> frozenset[str]:
    """Claude Code araç adlarını (`Read`, `Bash(git *)`, `mcp__s__t`) Fusion adlarına çevir.

    Claude Code'dan kopyalanan `--allowed-tools Read,Edit` eskiden bilinmeyen ad olarak
    kalıyor ve tur sessizce araçsız koşuyordu (31 Ekim). Büyük harfle başlayan ya da
    parantezli ad Claude biçimidir; küçük harfli adlar Fusion adı sayılıp aynen kalır.
    Parantez içi alt komut deseni (`Bash(git diff:*)`) Fusion'da yoktur: araç ailesinin
    tamamına uygulanır (izin listesinde onay yine sorulur, yasak listesinde tümü kapanır).
    """
    mapped: set[str] = set()
    for name in names:
        base = name.split("(", 1)[0].strip()
        if base.startswith(_CLAUDE_MCP_PREFIX) and base.count("__") >= 2:
            mapped.add(base[len(_CLAUDE_MCP_PREFIX) :])
            continue
        targets = CLAUDE_TOOL_MAP.get(base.lower())
        if targets and (base[:1].isupper() or base != name):
            mapped |= targets
            continue
        mapped.add(name)
    return frozenset(mapped)


def unknown_tool_message(unknown: Iterable[str], known: Iterable[str]) -> str:
    """Bilinmeyen araç adları için Türkçe hata; yakın adları önerir."""
    import difflib

    pool = sorted(set(known))
    names = sorted(set(unknown))
    suggestions = sorted(
        {match for name in names for match in difflib.get_close_matches(name, pool, n=2)}
    )
    hint = (
        messages.HEADLESS_TOOL_SUGGESTION.format(suggestions=", ".join(suggestions))
        if suggestions
        else ""
    )
    return messages.HEADLESS_UNKNOWN_TOOLS.format(names=", ".join(names), hint=hint)


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


def resolve_agent(
    name: str,
    *,
    home: Path,
    root: Path,
    managed_roots: tuple[Path, ...] = (),
    session_agents: tuple[Capability, ...] = (),
) -> Persona:
    """`--agent <ad>` tanımını (.claude/agents/<ad>.md) kişiliğe çevir; yoksa `ValueError`."""
    library = CapabilityRegistry(
        home,
        root,
        managed_roots=managed_roots,
        session_agents=session_agents,
        working_directory=root,
    )
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


class _LineReader:
    """stdin'i daemon iş parçacığında satır satır okuyup kuyruğa koyar.

    `asyncio.to_thread` kullanılmaz: bekleyen okuma varken `asyncio.run` kapanışı varsayılan
    yürütücüyü sonsuza dek bekler. Daemon iş parçacığı süreç çıkışını engellemez. Kuyruk
    `queue.Queue` olduğundan art arda gelen ayrı olay döngüleriyle de çalışır.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._eof = False

    def _start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._pump, name="fusion-onay-kanali", daemon=True
            )
            self._thread.start()

    def _pump(self) -> None:
        while True:
            try:
                line = self._stream.readline()
            except (OSError, ValueError):
                line = ""
            if not line:
                self._lines.put(_EOF)
                return
            self._lines.put(line)

    async def next_line(self, deadline: float) -> str | None:
        """Sıradaki satır; EOF ya da süre dolunca None."""
        if self._eof:
            return None
        self._start()
        while True:
            try:
                line = self._lines.get_nowait()
            except queue.Empty:
                if time.monotonic() >= deadline:
                    return None
                await asyncio.sleep(_POLL_INTERVAL)
                continue
            if line is _EOF:
                self._eof = True
                return None
            return line


class JsonLinesPrompter:
    """Onay ve soruları JSON-Lines ile dış sürece soran arayüz (`Prompter` + `UserAsker`)."""

    def __init__(
        self,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        timeout: float = DEFAULT_PERMISSION_TIMEOUT,
    ) -> None:
        self._reader = _LineReader(stdin or sys.stdin)
        self._stdout = stdout or sys.stdout
        self._timeout = timeout
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
                # Masaüstü hedefi (P-007): uygulama, kademe, uyarı, tıklanan öğe.
                "masaustu": (
                    request.desktop_target.payload() if request.desktop_target is not None else None
                ),
            }
        )
        reply = await self._read(istek_id)
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
        reply = await self._read(istek_id)
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

    async def _read(self, istek_id: str) -> Mapping[str, object] | None:
        """Beklenen kimliğe ait satırı bekle; EOF/bozuk satır/yanlış kimlik/süre → None.

        Daha önceki (zaman aşımına uğramış) bir isteğin geç cevabı atlanır.
        """
        deadline = time.monotonic() + self._timeout
        while True:
            line = await self._reader.next_line(deadline)
            if line is None:
                return None
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                return None
            if not isinstance(reply, dict):
                return None
            got = str(reply.get("istek_id", ""))
            if got == istek_id:
                return reply
            if not (got.isdigit() and int(got) < int(istek_id)):
                return None
