"""Temiz kabul alanına yalnız gerçek runtime gözlemini ve ortam kimliğini taşır."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

from evals.acceptance_command import AcceptanceCommand
from evals.research_runtime import RUNTIME_RECEIPT, RuntimeReceipt
from evals.tasks import EvalTask
from fusion_cli.core.evidence import EvidenceEnvironment
from fusion_cli.engines.agent.verify_discovery import evidence_environment


async def prepare_acceptance_evidence(
    root: Path,
    task: EvalTask,
    acceptance: AcceptanceCommand,
    receipt: RuntimeReceipt | None,
) -> EvidenceEnvironment | None:
    """Ajan makbuzunu yok say; ölçüt girdilerini gerçek bootstrap komutuna bağla."""
    await asyncio.to_thread(_write_receipt, root, receipt)
    if not task.criterion.command or not acceptance.command:
        return None
    environment = await asyncio.to_thread(
        evidence_environment,
        root,
        (task.criterion.command,),
        runtime=sys.version,
    )
    # Bootstrap ölçütü aynı yorumlayıcıda çalıştırır; kimliği dış komutu içerir.
    return replace(environment, command=acceptance.command) if environment else None


def _write_receipt(root: Path, receipt: RuntimeReceipt | None) -> None:
    path = root / RUNTIME_RECEIPT
    if path.exists():
        path.unlink()
    if receipt is not None:
        path.write_text(json.dumps(asdict(receipt), ensure_ascii=False), encoding="utf-8")
