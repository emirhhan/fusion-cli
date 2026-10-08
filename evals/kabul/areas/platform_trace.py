"""Platform B'nin okunur oynama izini doğrula; tarayıcı/state yazımı yapma.

Bu saf doğrulayıcı iz üretmez. Çağıran gerçek klavye turlarını, eş süreli tuşsuz
kontrolü ve kare kanıtlarını toplamalıdır. Kancanın kendi beyanı/kare hash'i tek
başına gerçek oyun kanıtı değildir; bağımsız observer adapter'ı henüz yoktur.
Eksik/ulaşılamayan gözlem UNVERIFIED, arena puanı platform başarısı değildir.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


class PlatformPhase(StrEnum):
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    WON = "won"
    LOST = "lost"


class TraceAction(StrEnum):
    START = "start_click"
    MOVE = "arrow_move"
    JUMP = "space_jump"
    DOOR = "door_contact"
    PAUSE = "pause_wait"
    RESUME = "resume"
    WAIT = "natural_wait"
    RESTART = "restart"


class TraceStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class PlatformSnapshot:
    phase: PlatformPhase
    level: int
    player: tuple[float, float] | None
    remaining_keys: frozenset[str] | None
    gate_contact: bool | None
    health: float | None
    score: float | None
    transient_ids: frozenset[str] | None
    #: Okunur simülasyon özeti; menü/overlay pikselinden ayrı tutulur.
    world_digest: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.phase, PlatformPhase)
            or type(self.level) is not int
            or self.level < 0
        ):
            raise ValueError("Platform evresi/bölümü geçersiz.")
        for value in (self.health, self.score, *(self.player or ())):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("Platform sayısal gözlemi sonlu olmalı.")
        if self.player is not None and (
            not isinstance(self.player, tuple) or len(self.player) != 2
        ):
            raise ValueError("Oyuncu geometrisi iki koordinat olmalı.")
        if self.gate_contact is not None and type(self.gate_contact) is not bool:
            raise ValueError("Kapı teması bool gözlem olmalı.")
        for identifiers in (self.remaining_keys, self.transient_ids):
            if identifiers is not None and (
                not isinstance(identifiers, frozenset)
                or any(not isinstance(item, str) or not item for item in identifiers)
            ):
                raise ValueError("Nesne kimlikleri değişmez gözlem kümesi olmalı.")
        if self.world_digest is not None and (
            not isinstance(self.world_digest, str) or not _DIGEST.fullmatch(self.world_digest)
        ):
            raise ValueError("Dünya özeti SHA-256 olmalı.")


@dataclass(frozen=True, slots=True)
class TraceEvent:
    action: TraceAction
    before: PlatformSnapshot
    after: PlatformSnapshot
    idle_after: PlatformSnapshot | None = None
    #: Gerçek önce/sonra kare dosyalarının özetleri; ham yol/metin tutulmaz.
    frame_digests: tuple[str, ...] = ()
    read_only: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.before, PlatformSnapshot)
            or not isinstance(self.after, PlatformSnapshot)
            or (self.idle_after is not None and not isinstance(self.idle_after, PlatformSnapshot))
        ):
            raise ValueError("Oynama izi gözlemleri typed snapshot olmalı.")
        if not isinstance(self.action, TraceAction) or type(self.read_only) is not bool:
            raise ValueError("Oynama izi eylemi geçersiz.")
        if not isinstance(self.frame_digests, tuple) or any(
            not isinstance(item, str) or not _DIGEST.fullmatch(item) for item in self.frame_digests
        ):
            raise ValueError("Kare kanıtı SHA-256 tuple olmalı.")


@dataclass(frozen=True, slots=True)
class TraceCriterion:
    name: str
    status: TraceStatus


@dataclass(frozen=True, slots=True)
class PlatformTraceReport:
    criteria: tuple[TraceCriterion, ...]

    @property
    def status(self) -> TraceStatus:
        statuses = {item.status for item in self.criteria}
        if TraceStatus.FAILED in statuses:
            return TraceStatus.FAILED
        if not statuses or TraceStatus.UNVERIFIED in statuses:
            return TraceStatus.UNVERIFIED
        return TraceStatus.PASSED

    @property
    def complete(self) -> bool:
        return self.status is TraceStatus.PASSED


def _eligible(event: TraceEvent) -> bool:
    return event.read_only and len(event.frame_digests) >= 2


def _aggregate(results: list[bool | None]) -> TraceStatus:
    if False in results:
        return TraceStatus.FAILED
    return TraceStatus.PASSED if True in results else TraceStatus.UNVERIFIED


def _world(snapshot: PlatformSnapshot) -> tuple[object, ...] | None:
    if any(
        value is None
        for value in (
            snapshot.player,
            snapshot.remaining_keys,
            snapshot.health,
            snapshot.score,
            snapshot.transient_ids,
            snapshot.world_digest,
        )
    ):
        return None
    return (
        snapshot.level,
        snapshot.player,
        snapshot.remaining_keys,
        snapshot.health,
        snapshot.score,
        snapshot.transient_ids,
        snapshot.world_digest,
    )


def _input(event: TraceEvent, *, jump: bool) -> bool | None:
    before, after, idle = event.before, event.after, event.idle_after
    if before.player is None or after.player is None or idle is None or idle.player is None:
        return None
    if (
        before.phase is not PlatformPhase.PLAYING
        or after.phase is not PlatformPhase.PLAYING
        or idle.phase is not PlatformPhase.PLAYING
    ):
        return False
    return after.player[1] < idle.player[1] if jump else after.player[0] != idle.player[0]


def _locked_door(event: TraceEvent) -> bool | None:
    before, after = event.before, event.after
    if before.remaining_keys is None or before.gate_contact is None:
        return None
    if not before.remaining_keys or not before.gate_contact:
        return None
    return after.level == before.level and after.phase is PlatformPhase.PLAYING


def _advance(event: TraceEvent) -> bool | None:
    before, after = event.before, event.after
    if after.level == before.level:
        return None
    if before.remaining_keys is None or before.gate_contact is None:
        return None
    return (
        before.level in (1, 2)
        and after.level == before.level + 1
        and before.phase is PlatformPhase.PLAYING
        and after.phase is PlatformPhase.PLAYING
        and before.gate_contact
        and not before.remaining_keys
    )


def _win(event: TraceEvent) -> bool | None:
    before, after = event.before, event.after
    if after.phase is not PlatformPhase.WON:
        return None
    if before.remaining_keys is None or before.gate_contact is None:
        return None
    return (
        before.level == after.level == 3
        and before.phase is PlatformPhase.PLAYING
        and before.gate_contact
        and not before.remaining_keys
    )


def _pause(event: TraceEvent) -> bool | None:
    before, after = _world(event.before), _world(event.after)
    if before is None or after is None:
        return None
    return event.before.phase is event.after.phase is PlatformPhase.PAUSED and before == after


def _restart(event: TraceEvent, baseline: PlatformSnapshot | None) -> bool | None:
    if baseline is None or _world(baseline) is None or _world(event.after) is None:
        return None
    return (
        event.before.phase in (PlatformPhase.LOST, PlatformPhase.WON)
        and event.after.phase is PlatformPhase.PLAYING
        and event.after.level == 1
        and event.after.player == baseline.player
        and event.after.remaining_keys == baseline.remaining_keys
        and event.after.health == baseline.health
        and event.after.score == baseline.score
        and event.after.transient_ids == baseline.transient_ids
    )


def _event_invariant(event: TraceEvent) -> bool | None:
    before, after = event.before, event.after
    if event.action is TraceAction.START:
        return (
            before.phase is PlatformPhase.MENU
            and after.phase is PlatformPhase.PLAYING
            and after.level == 1
        )
    if event.action is TraceAction.RESTART:
        return (
            before.phase in (PlatformPhase.WON, PlatformPhase.LOST)
            and after.phase is PlatformPhase.PLAYING
            and after.level == 1
        )
    if after.level != before.level:
        return _advance(event) if event.action is TraceAction.DOOR else False
    if after.phase is PlatformPhase.WON and before.phase is not PlatformPhase.WON:
        return _win(event) if event.action is TraceAction.DOOR else False
    if after.phase is PlatformPhase.LOST and before.phase is not PlatformPhase.LOST:
        return (
            None
            if after.health is None
            else before.phase is PlatformPhase.PLAYING and after.health <= 0
        )
    return not (
        before.phase in (PlatformPhase.WON, PlatformPhase.LOST) and after.phase is not before.phase
    )


def _new_results() -> dict[str, list[bool | None]]:
    return {
        name: []
        for name in (
            "start",
            "movement",
            "jump",
            "locked_door",
            "level_sequence",
            "win",
            "pause",
            "resume",
            "loss",
            "restart",
            "trace_integrity",
            "event_invariants",
        )
    }


def verify_trace(events: tuple[TraceEvent, ...]) -> PlatformTraceReport:
    """Ölçülen eylemleri denetle; eksik route/observer kapılarını geçirme."""
    if not isinstance(events, tuple) or any(not isinstance(item, TraceEvent) for item in events):
        raise ValueError("Oynama izi typed değişmez event tuple olmalı.")
    observed = tuple(item for item in events if _eligible(item))
    starts = [item for item in observed if item.action is TraceAction.START]
    baseline = starts[0].after if starts else None
    results = _new_results()
    results["trace_integrity"].append(True if events and len(observed) == len(events) else None)
    transitions: list[tuple[int, int]] = []
    for event in observed:
        before, after = event.before, event.after
        results["event_invariants"].append(_event_invariant(event))
        if event.action is TraceAction.START:
            results["start"].append(
                before.phase is PlatformPhase.MENU
                and after.phase is PlatformPhase.PLAYING
                and after.level == 1
            )
        elif event.action in (TraceAction.MOVE, TraceAction.JUMP):
            jump = event.action is TraceAction.JUMP
            results["jump" if jump else "movement"].append(_input(event, jump=jump))
        elif event.action is TraceAction.DOOR:
            results["locked_door"].append(_locked_door(event))
            advance = _advance(event)
            if advance is not None:
                results["level_sequence"].append(advance)
                if advance:
                    transitions.append((before.level, after.level))
            results["win"].append(_win(event))
        elif event.action is TraceAction.PAUSE:
            results["pause"].append(_pause(event))
        elif event.action is TraceAction.RESUME:
            results["resume"].append(
                before.phase is PlatformPhase.PAUSED and after.phase is PlatformPhase.PLAYING
            )
        elif event.action is TraceAction.RESTART:
            results["restart"].append(_restart(event, baseline))
        elif event.action is TraceAction.WAIT and after.phase is PlatformPhase.LOST:
            results["loss"].append(
                None
                if after.health is None
                else before.phase is PlatformPhase.PLAYING and after.health <= 0
            )
    if False not in results["level_sequence"]:
        results["level_sequence"] = [True] if transitions == [(1, 2), (2, 3)] else []
    if None in results["event_invariants"] and False not in results["event_invariants"]:
        results["event_invariants"] = []
    return PlatformTraceReport(
        tuple(TraceCriterion(name, _aggregate(items)) for name, items in results.items())
    )
