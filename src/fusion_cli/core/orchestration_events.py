"""Ajan ekipleri (P-061) ve dinamik iş akışlarının (P-062) arayüz olayları.

Alt ajanların kendi kartları `SubAgentStarted`/`SubAgentFinished` ile akmaya devam eder;
bu olaylar onların ÜSTÜNDEKİ panoyu taşır: ekibin paylaşımlı görev listesi ve posta
kutusu, iş akışının evresi ve düğüm durumları. Her olay panonun TAM anlık görüntüsüdür;
arayüz farkı birleştirmez, son olayı çizer (sırasız/kayıp olayda pano bozulmaz).
"""

from __future__ import annotations

from dataclasses import dataclass

from .events import Event


@dataclass(frozen=True, slots=True)
class TeamTaskView:
    """Paylaşımlı görev listesindeki bir satır."""

    id: str
    title: str
    #: bekliyor | calisiyor | tamam | basarisiz
    status: str
    owner: str = ""
    depends_on: tuple[str, ...] = ()
    result: str = ""


@dataclass(frozen=True, slots=True)
class TeamMemberView:
    """Ekip üyesinin panodaki durumu."""

    name: str
    persona: str
    #: bekliyor | sirada (yazma alanı kapısında) | calisiyor | bosta | bitti
    status: str
    #: Üyenin SON koşusunun alt ajan kimliği (kartı bununla bulunur).
    sub_id: str = ""
    wakes: int = 0


@dataclass(frozen=True, slots=True)
class TeamMessageView:
    """Posta kutusundaki bir mesaj (kırpılmış)."""

    sender: str
    recipient: str
    text: str
    at: float = 0.0


@dataclass(frozen=True, slots=True)
class TeamBoardChanged(Event):
    """Ekip panosu değişti: görev alındı/bitti, mesaj gitti, üye boşa düştü."""

    team: str
    goal: str = ""
    #: calisiyor | bitti | durdu
    status: str = "calisiyor"
    tasks: tuple[TeamTaskView, ...] = ()
    members: tuple[TeamMemberView, ...] = ()
    messages: tuple[TeamMessageView, ...] = ()
    #: Masaüstünde bu ekibin ajan kartlarının toplandığı grup boyu (`SubAgentStarted`).
    group_size: int = 1


@dataclass(frozen=True, slots=True)
class WorkflowNodeView:
    """İş akışındaki bir ajan düğümünün durumu."""

    id: str
    label: str
    #: bekliyor | calisiyor | tamam | basarisiz | iptal | atlandi
    status: str
    phase: str = ""
    sub_id: str = ""
    summary: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowProgress(Event):
    """Dinamik iş akışının ilerlemesi (`/workflows` ve masaüstü panosu bundan çizer)."""

    run_id: str
    name: str
    #: calisiyor | tamam | yarim | iptal | hata
    status: str
    phase: str = ""
    agents_started: int = 0
    agents_limit: int = 0
    nodes: tuple[WorkflowNodeView, ...] = ()
    elapsed_s: float = 0.0
    message: str = ""
