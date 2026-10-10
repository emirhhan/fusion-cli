"""Gerçek zamanlama rotalarını yalıtılmış JSON satırlarıyla sürer."""

from __future__ import annotations

import json
import sys
from datetime import datetime, tzinfo
from pathlib import Path

from fusion_cli.appserver import schedule


class ControlledDateTime(datetime):
    """Rotaların varsayılan saatini testin belirlediği anda tutar."""

    timestamp_value: float = 0

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> ControlledDateTime:
        return cls.fromtimestamp(cls.timestamp_value, tz)


def main() -> None:
    """Yalnız seçilen geçici depoya erişerek kayıtlı rotaları çağırır."""
    target = Path(sys.argv[1])
    schedule.schedules_path = lambda: target
    # The route module imports datetime privately; replace its clock for this process.
    schedule.datetime = ControlledDateTime  # type: ignore[attr-defined]
    for line in sys.stdin:
        request = json.loads(line)
        if request["route"] == "clock":
            ControlledDateTime.timestamp_value = float(request["timestamp"])
            response = {"ok": True}
        else:
            response = schedule.SCHEDULE_ROUTES[request["route"]](request.get("data", {}))
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
