"""Tur transkripti — başarısızlığı SONRADAN teşhis edebilmek için.

Eval yalnızca geç/kal ve çağrı sayısı kaydediyordu. Ölçüldü ki zor görevlerde
agent bimodal davranıyor: ya işi yapıyor ya hiç dokunmuyor. "Neden hiçbir şey
yapmadı" sorusu sonucu bilerek cevaplanamaz; turda NE OLDUĞUNA bakmak gerekir ve
bu, her teşhis için görevi elle canlı koşmayı zorunlu kılıyordu.

Kaydedilen: araç çağrıları (adı, sonucu, kırpılmış çıktısı) ve model çağrılarının
özeti. Kaydedilmeyen: akış parçaları (`TokenReceived`) — binlerce satır üretir ve
teşhise hiçbir şey katmaz.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fusion_cli.core.events import (
    Event,
    ModelCallFinished,
    ToolExecuted,
)

#: Araç çıktısından transkripte alınacak en fazla karakter. Tam çıktı transkripti
#: okunamaz hale getirir; teşhis için baş taraf yeterlidir (hata genelde orada).
_MAX_OUTPUT_CHARS = 1_000


class TranscriptRecorder:
    """Olayları JSONL olarak dosyaya yazan yayıncı.

    `EventPublisher` protokolünü karşılar; motor bunu normal bir yayıncı sanır.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8")

    def publish(self, event: Event) -> None:
        satir = _to_row(event)
        if satir is None:
            return
        self._handle.write(json.dumps(satir, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def _to_row(event: Event) -> dict[str, Any] | None:
    """Olayı transkript satırına çevir; teşhise katkısı yoksa None."""
    if isinstance(event, ToolExecuted):
        return {
            "event": "ToolExecuted",
            "name": event.name,
            "args": {k: _kisalt(str(v)) for k, v in event.args.items()},
            "outcome": event.outcome.value,
            "output": _kisalt(event.output),
        }
    if isinstance(event, ModelCallFinished):
        return {
            "event": "ModelCallFinished",
            "role": event.role,
            "ok": event.result.ok,
            "error": event.result.error,
            "tool_calls": [call.name for call in event.result.tool_calls],
            "text": _kisalt(event.result.text),
        }
    return None


def _kisalt(text: str) -> str:
    return text if len(text) <= _MAX_OUTPUT_CHARS else text[:_MAX_OUTPUT_CHARS] + "…[kırpıldı]"
