"""Gerçek Page girdisi/kareleri; görünen DOM semantiği yoksa iz doğrulanmaz.

Canvas/OCR veya oyun kancasından semantik çıkarımı desteklenmez. DOM sözleşmesi
[data-platform-screen], görünür level/health/score metinleri, player/key/door/object
öğeleridir. Marker olmayan ürünü yamamak veya state yazmak bu modülün işi değildir.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from evals.kabul.areas.platform_trace import (
    PlatformPhase,
    PlatformSnapshot,
    TraceAction,
    TraceEvent,
)

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_KEYS = frozenset({"ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Space", "p", "r"})
_READ_DOM = """() => {
  const visible = el => { const s=getComputedStyle(el), r=el.getBoundingClientRect();
    if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0||
       r.width<=0||r.height<=0||r.right<=0||r.bottom<=0||r.left>=innerWidth||r.top>=innerHeight)
      return false;
    const top=document.elementFromPoint(Math.max(0,Math.min(innerWidth-1,r.left+r.width/2)),
      Math.max(0,Math.min(innerHeight-1,r.top+r.height/2)));
    return top && (el===top||el.contains(top)); };
  const nodes=selector=>Array.from(document.querySelectorAll(selector)).filter(visible);
  const one=selector=>{const found=nodes(selector);return found.length===1?found[0]:null;};
  const screen=one('[data-platform-screen]'), player=one('[data-platform-player]');
  const number=selector=>{const el=one(selector);if(!el)return null;
    const text=el.textContent.trim();return /^-?\\d+(\\.\\d+)?$/.test(text)?Number(text):null;};
  if(!screen||!player)return null;
  const rect=player.getBoundingClientRect(), door=one('[data-platform-door]');
  const allKeys=Array.from(screen.querySelectorAll('[data-platform-key]'));
  const keys=allKeys.filter(visible), objects=nodes('[data-platform-object]');
  const keysComplete=keys.length===allKeys.length;
  const geometry=Array.from(new Set([player,...keys,...objects,...(door?[door]:[])]))
    .map(el=>{const r=el.getBoundingClientRect();return [el.id,r.x,r.y,r.width,r.height];});
  const contact=door?(()=>{const d=door.getBoundingClientRect();
    return rect.left<d.right&&rect.right>d.left&&rect.top<d.bottom&&rect.bottom>d.top;})():null;
  return {phase:screen.getAttribute('data-platform-screen'),level:number('[data-platform-level]'),
    player:[rect.x,rect.y],keys:keys.map(el=>el.id),keys_complete:keysComplete,contact,
    health:number('[data-platform-health]'),score:number('[data-platform-score]'),
    objects:objects.map(el=>el.id),geometry};
}"""


class PlatformKeys(Protocol):
    def down(self, key: str) -> None: ...
    def up(self, key: str) -> None: ...


class PlatformPage(Protocol):
    @property
    def keyboard(self) -> PlatformKeys: ...
    def evaluate(self, script: str) -> object: ...
    def screenshot(self) -> bytes: ...
    def click(self, selector: str) -> None: ...
    def wait_for_timeout(self, timeout: float) -> None: ...


@dataclass(frozen=True, slots=True)
class RouteStep:
    action: TraceAction
    keys: tuple[str, ...]
    duration_ms: int
    click_selector: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.action, TraceAction)
            or type(self.duration_ms) is not int
            or self.duration_ms <= 0
            or not isinstance(self.keys, tuple)
            or any(not isinstance(key, str) or key not in _KEYS for key in self.keys)
        ):
            raise ValueError("Platform route eylemi/tuşları/süresi geçersiz.")
        if self.action is TraceAction.START and (self.keys or not self.click_selector):
            raise ValueError("Başla gerçek click gerektirir; keyboard fallback yok.")
        if self.click_selector is not None and (
            not isinstance(self.click_selector, str) or not self.click_selector.strip()
        ):
            raise ValueError("Route click selector geçersiz.")
        _validate_action_keys(self)


def _validate_action_keys(step: RouteStep) -> None:
    keys = frozenset(step.keys)
    horizontal = frozenset({"ArrowLeft", "ArrowRight"})
    if len(keys) != len(step.keys):
        raise ValueError("Route eylem tuşları yinelenemez.")
    valid = {
        TraceAction.START: not keys and step.click_selector is not None,
        TraceAction.MOVE: bool(keys) and keys <= horizontal and step.click_selector is None,
        TraceAction.JUMP: "Space" in keys
        and keys <= horizontal | {"Space"}
        and step.click_selector is None,
        TraceAction.PAUSE: keys == {"p"} and step.click_selector is None,
        TraceAction.RESUME: keys == {"p"} and step.click_selector is None,
        TraceAction.RESTART: (keys == {"r"} and step.click_selector is None)
        or (not keys and step.click_selector is not None),
        TraceAction.WAIT: not keys and step.click_selector is None,
        TraceAction.DOOR: keys <= horizontal | {"Space"} and step.click_selector is None,
    }
    if not valid[step.action]:
        raise ValueError("Route eylem etiketi gerçek girdiyle eşleşmiyor.")


@dataclass(frozen=True, slots=True)
class CapturedObservation:
    snapshot: PlatformSnapshot | None
    frame_digest: str
    frame_name: str


@dataclass(frozen=True, slots=True)
class ObservedRoute:
    steps: tuple[RouteStep, ...]
    events: tuple[TraceEvent, ...]
    observations: tuple[CapturedObservation, ...]
    source_digest: str
    unverified_steps: tuple[int, ...]


def _identifiers(raw: object) -> frozenset[str] | None:
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item for item in raw):
        return None
    if len(raw) != len(set(raw)):
        return None
    return frozenset(hashlib.sha256(item.encode()).hexdigest() for item in raw)


def _snapshot(raw: object) -> PlatformSnapshot | None:
    if not isinstance(raw, dict):
        return None
    try:
        phase, level = raw.get("phase"), raw.get("level")
        if not isinstance(phase, str) or type(level) is not int:
            return None
        player = raw.get("player")
        if not isinstance(player, list) or len(player) != 2:
            return None
        geometry = raw.get("geometry")
        if not isinstance(geometry, list) or not geometry:
            return None
        world = json.dumps(
            {
                key: raw.get(key)
                for key in ("level", "player", "keys", "health", "score", "objects", "geometry")
            },
            sort_keys=True,
            allow_nan=False,
        ).encode()
        return PlatformSnapshot(
            PlatformPhase(phase),
            level,
            tuple(player),
            _identifiers(raw.get("keys")) if raw.get("keys_complete") is True else None,
            raw.get("contact"),
            raw.get("health"),
            raw.get("score"),
            _identifiers(raw.get("objects")),
            hashlib.sha256(world).hexdigest(),
        )
    except (ValueError, TypeError):
        return None


def _capture(page: PlatformPage, output: Path, name: str) -> CapturedObservation:
    snapshot = _snapshot(page.evaluate(_READ_DOM))
    frame = page.screenshot()
    (output / name).write_bytes(frame)
    return CapturedObservation(snapshot, hashlib.sha256(frame).hexdigest(), name)


def _perform(
    page: PlatformPage, step: RouteStep, output: Path, index: int
) -> CapturedObservation | None:
    if step.click_selector is not None:
        page.click(step.click_selector)
    pressed: list[str] = []
    try:
        for key in step.keys:
            page.keyboard.down(key)
            pressed.append(key)
        paused = (
            _capture(page, output, f"step-{index}-paused.png")
            if step.action is TraceAction.PAUSE
            else None
        )
        page.wait_for_timeout(step.duration_ms)
        return paused
    finally:
        for key in reversed(pressed):
            page.keyboard.up(key)


def _matched_idle(
    before: CapturedObservation, idle_before: CapturedObservation, idle_after: CapturedObservation
) -> PlatformSnapshot | None:
    return idle_after.snapshot if before.snapshot == idle_before.snapshot else None


def _pause_baseline(
    before: CapturedObservation,
    paused: CapturedObservation,
    step: RouteStep,
    observations: list[CapturedObservation],
    events: list[TraceEvent],
) -> CapturedObservation:
    observations.append(before)
    if before.snapshot is not None and paused.snapshot is not None:
        initial, after_press = before.snapshot, paused.snapshot
        if (
            initial.level != after_press.level
            or initial.phase is not PlatformPhase.PLAYING
            or after_press.phase is not PlatformPhase.PAUSED
        ):
            events.append(
                TraceEvent(
                    step.action,
                    initial,
                    after_press,
                    frame_digests=(before.frame_digest, paused.frame_digest),
                )
            )
    return paused


def collect_trace(
    play: PlatformPage,
    idle: PlatformPage | None,
    steps: tuple[RouteStep, ...],
    output: Path,
    *,
    source_digest: str,
) -> ObservedRoute:
    """Sayfaları açmaz; gerçek input/kare toplar, eksik route'yi geçirmez.

    Idle sayfa aynı route prefix'inden çağıranca hazırlanmış olmalı. Eşleşmeyen
    başlangıçta input kontrolü kullanılmaz. Bu fonksiyon reset/teleport yapmaz.
    """
    if not isinstance(source_digest, str) or not _DIGEST.fullmatch(source_digest):
        raise ValueError("Üretilmiş public kaynak özeti SHA-256 olmalı.")
    if not isinstance(steps, tuple) or any(not isinstance(step, RouteStep) for step in steps):
        raise ValueError("Route typed değişmez tuple olmalı.")
    if output.exists():
        raise ValueError("Observer kanıt klasörü yeni olmalı; üzerine yazılmaz.")
    output.mkdir(parents=True)
    events: list[TraceEvent] = []
    observations: list[CapturedObservation] = []
    unverified: list[int] = []
    for index, step in enumerate(steps):
        before = _capture(play, output, f"step-{index}-before.png")
        idle_before = _capture(idle, output, f"step-{index}-idle-before.png") if idle else None
        paused_before = _perform(play, step, output, index)
        if paused_before is not None:
            if before.snapshot is None:
                unverified.append(index)
            before = _pause_baseline(before, paused_before, step, observations, events)
        if idle:
            idle.wait_for_timeout(step.duration_ms)
        after = _capture(play, output, f"step-{index}-after.png")
        idle_after = _capture(idle, output, f"step-{index}-idle-after.png") if idle else None
        observations.extend((before, after))
        control = None
        if idle_before is not None and idle_after is not None:
            observations.extend((idle_before, idle_after))
            control = _matched_idle(before, idle_before, idle_after)
        if before.snapshot is None or after.snapshot is None:
            unverified.append(index)
            continue
        events.append(
            TraceEvent(
                step.action,
                before.snapshot,
                after.snapshot,
                control,
                (before.frame_digest, after.frame_digest),
            )
        )
    return ObservedRoute(
        steps, tuple(events), tuple(observations), source_digest, tuple(unverified)
    )
