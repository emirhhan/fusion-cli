"""Ekip (P-061) ve iş akışı (P-062) panolarının terminal karşılığı: tek satırlık ilerleme.

Masaüstü her `WorkflowProgress` / `TeamBoardChanged` olayında panoyu yeniden çizer;
terminalde her düğüm değişikliği için satır basmak alt ajan satırlarıyla birlikte ekranı
boğar. Burada satır yalnız ANLAMLI durum değişince üretilir: iş akışında koşu durumu ya
da evre, ekipte ekip durumu, biten görev sayısı ya da üye durumları. Ölçüldü (31 Ekim):
`ui/renderer.py` bu iki olayı hiç işlemiyordu; terminal kullanıcısı koşunun evresini,
kimliğini (iptal için) ve ekibin görev panosunu göremiyordu.
"""

from __future__ import annotations

from ..core.orchestration_events import TeamBoardChanged, WorkflowProgress
from . import messages

_RUN_STATUS = {
    "calisiyor": "çalışıyor",
    "tamam": "tamamlandı",
    "yarim": "yarım kaldı",
    "iptal": "iptal edildi",
    "hata": "hata",
}
_TEAM_STATUS = {"calisiyor": "çalışıyor", "bitti": "tamamlandı", "durdu": "durdu"}
_MEMBER_STATUS = {
    "bekliyor": "bekliyor",
    "sirada": "sırada",
    "calisiyor": "çalışıyor",
    "bosta": "boşta",
    "bitti": "bitti",
}
_FINISHED_NODE = frozenset({"tamam", "basarisiz", "iptal", "atlandi"})


class OrchestrationLines:
    """Olaydan satır üret; aynı koşu/ekip için önemli bir şey değişmediyse None."""

    def __init__(self) -> None:
        self._seen: dict[str, tuple[object, ...]] = {}

    def workflow(self, event: WorkflowProgress) -> list[str]:
        key = f"akis:{event.run_id}"
        signature = (event.status, event.phase)
        if self._seen.get(key) == signature:
            return []
        first = key not in self._seen
        self._seen[key] = signature
        total = len(event.nodes)
        lines = []
        if first and event.status == "calisiyor":
            lines.append(
                messages.AKIS_STARTED.format(name=event.name, total=total, run_id=event.run_id)
            )
        done = sum(node.status in _FINISHED_NODE for node in event.nodes)
        lines.append(
            messages.AKIS_PROGRESS.format(
                name=event.name,
                status=_RUN_STATUS.get(event.status, event.status),
                phase=f" · evre: {event.phase}" if event.phase else "",
                done=done,
                total=total,
                agents=event.agents_started,
                limit=event.agents_limit,
            )
        )
        if event.message and event.status != "calisiyor":
            lines.append(event.message)
        return lines

    def team(self, event: TeamBoardChanged) -> list[str]:
        key = f"ekip:{event.team}"
        done = sum(task.status == "tamam" for task in event.tasks)
        states = tuple((member.name, member.status) for member in event.members)
        signature = (event.status, done, len(event.tasks), states)
        if self._seen.get(key) == signature:
            return []
        self._seen[key] = signature
        members = ", ".join(
            f"{name} {_MEMBER_STATUS.get(status, status)}" for name, status in states
        )
        return [
            messages.EKIP_PROGRESS.format(
                team=event.team,
                status=_TEAM_STATUS.get(event.status, event.status),
                done=done,
                total=len(event.tasks),
                members=members or "üye yok",
            )
        ]
