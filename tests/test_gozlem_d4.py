"""Gözlemlenebilirlik düzeltmeleri (30 Ekim triyajı: C1-22, C1-23, C1-24, C1-53, C1-55)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.events import (
    FusionCompleted,
    ModelCallFinished,
    StatusChanged,
    ToolExecuted,
    ToolOutcome,
)
from fusion_cli.core.types import ModelResult
from fusion_cli.observability import audit as denetim
from fusion_cli.observability.audit import AuditSink, audit_path, read_recent
from fusion_cli.observability.bus import EventBus
from fusion_cli.observability.trace_store import TraceStore
from fusion_cli.observability.tracing import LangfuseTracer

from .fakes import RecordingSink

SIR = "sk-" + "a1b2c3d4e5f6g7h8i9j0k1"


def _arac(args: dict[str, object], cikti: str = "tamam") -> ToolExecuted:
    return ToolExecuted(name="write_file", args=args, output=cikti, outcome=ToolOutcome.OK)


def test_denetim_uzun_icerigi_kisaltir_yolu_korur(tmp_path: Path) -> None:
    sink = AuditSink(tmp_path, "sohbet", root=tmp_path)

    sink.handle(_arac({"path": "src/a.py", "content": "x" * 50_000}))

    kayit = read_recent(audit_path(tmp_path, "sohbet"), 1)[0]
    args = json.loads(str(kayit["argumanlar"]))
    assert args["path"] == "src/a.py"
    assert len(args["content"]) < denetim.AUDIT_ARG_CHARS + 40
    assert "+49700 karakter" in args["content"]


def test_denetim_donmesi_birden_cok_yedek_tutar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(denetim, "AUDIT_MAX_BYTES", 200)
    sink = AuditSink(tmp_path, "sohbet", root=tmp_path)

    for i in range(12):
        sink.handle(_arac({"path": f"dosya{i}.py"}))

    adlar = sorted(p.name for p in tmp_path.iterdir())
    assert "sohbet.jsonl.1" in adlar and "sohbet.jsonl.2" in adlar


class _Gozlem:
    def __init__(self) -> None:
        self.cagrilar: list[dict[str, object]] = []

    def start_observation(self, **kwargs: object) -> _Gozlem:
        self.cagrilar.append(kwargs)
        return self

    def update(self, **kwargs: object) -> None:
        self.cagrilar.append(kwargs)

    def end(self) -> None:
        pass


def test_langfuse_gonderilen_hicbir_alan_sir_tasimaz() -> None:
    izleyici = LangfuseTracer.__new__(LangfuseTracer)
    izleyici._client = None
    gozlem = _Gozlem()
    izleyici._root = gozlem
    izleyici.disabled_reason = None

    izleyici.handle(_arac({"command": f"curl -H 'Authorization: Bearer {SIR}'"}, f"anahtar {SIR}"))
    izleyici.handle(
        ModelCallFinished(
            role="agent",
            result=ModelResult(
                name="a", model="m", text=f"şu anahtar {SIR}", latency_ms=1, ok=True
            ),
        )
    )
    izleyici.handle(FusionCompleted(result=SimpleNamespace(final_answer=f"son {SIR}")))  # type: ignore[arg-type]

    assert SIR not in json.dumps(gozlem.cagrilar, default=str)


async def test_baska_is_parcacigindan_yayin_siralamayi_bozmaz() -> None:
    sink = RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(sink)
        await asyncio.to_thread(lambda: [bus.publish(StatusChanged(f"t-{i}")) for i in range(20)])
        await bus.drain()

    assert [e.message for e in sink.events] == [f"t-{i}" for i in range(20)]


async def test_failures_listesi_sinirsiz_buyumez() -> None:
    from .fakes import ExplodingSink

    async with EventBus() as bus:
        bus.subscribe(ExplodingSink())
        for i in range(500):
            bus.publish(StatusChanged(f"x{i}"))
        await bus.drain()

    assert 0 < len(bus.failures) <= 200


def test_iz_listesi_kaybolan_dosyada_cokmez(tmp_path: Path, monkeypatch) -> None:
    depo = TraceStore(tmp_path)
    for ad in ("a", "b"):
        depo.writer(ad).close()
    gercek = Path.stat

    def stat(self: Path, *a: object, **k: object):
        if self.name == "a.jsonl":
            raise FileNotFoundError(self)
        return gercek(self, *a, **k)

    monkeypatch.setattr(Path, "stat", stat)

    assert depo.runs() == ("b",)
