"""Per-actor acknowledgement of an exact captured screen observation."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from threading import Lock

from ...core.desktop_frame import DesktopCapture, DesktopMouseAction, image_payload_digest
from ...core.errors import PathAccessError
from ...core.tools import ToolArgs, ToolContext, ToolResult
from ...core.types import Message
from ...tools.files import resolve_path

Owner = tuple[str, str, str, int, str]
GROUNDING_REQUIRED = (
    "Güncel ekran gözlemi bu işlemden önce modele ulaşmadı. Önce desktop_screenshot al; "
    "model görsel okuyamıyorsa aynı dosyayı view_image(path, question) ile incele. "
    "Gözlemi aldıktan sonraki model adımında koordinat seç; aynı araç grubunda görüntü "
    "alıp görmeden tıklama. Erişilebilirlik başvuruları ve klavye araçları da kullanılabilir."
)


def owner(context: ToolContext, conversation_id: str, attempt_id: str | None) -> Owner:
    return (
        str(context.root),
        conversation_id,
        attempt_id or "",
        id(context.desktop),
        context.job_scope,
    )


def current_capture(context: ToolContext) -> DesktopCapture | None:
    capture = context.desktop.current_capture
    if (
        capture is None
        or not context.desktop.capture_is_current((capture.generation, capture.focus))
        or capture.frame != context.desktop.frame
        or capture.focus != context.desktop.focus_identity()
    ):
        return None
    return capture


@dataclass(frozen=True, slots=True)
class PendingObservation:
    capture: DesktopCapture
    message: Message
    owner: Owner


@dataclass(frozen=True, slots=True)
class RequestObservation:
    capture: DesktopCapture
    owner: Owner
    direct_image: bool
    helper: bool


@dataclass(frozen=True, slots=True)
class HeldMouse:
    button: int
    point: tuple[float, float]
    owner: Owner
    context: ToolContext


@dataclass
class DesktopGrounding:
    """Authority belongs to one drive, never to a shared DesktopView."""

    pending: list[PendingObservation] = field(default_factory=list)
    acknowledged: RequestObservation | None = None
    token: object = field(default_factory=object, repr=False)
    held: dict[int, HeldMouse] = field(default_factory=dict)
    closed: bool = False
    cleanup_error: str = ""
    _cleanup_errors: dict[int, str] = field(default_factory=dict, repr=False)
    failure_reporter: Callable[[str], None] | None = field(default=None, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def mouse_context(
        self, context: ToolContext, conversation_id: str, attempt_id: str | None
    ) -> ToolContext:
        return replace(
            context,
            desktop_coordinate_frame=self.acknowledged.capture.frame
            if self.acknowledged is not None
            else None,
            desktop_mouse_owner=self.token,
            desktop_mouse_observer=lambda action: self.observe_mouse(
                action, context, conversation_id, attempt_id
            ),
            desktop_mouse_guard=lambda name, args: self.preflight(
                name, args, context, conversation_id, attempt_id
            ),
        )

    def observe_mouse(
        self,
        action: DesktopMouseAction,
        context: ToolContext,
        conversation_id: str,
        attempt_id: str | None,
    ) -> None:
        scope = owner(context, conversation_id, attempt_id)
        with self._lock:
            if action.pressed is not None:
                self.held[action.pressed] = HeldMouse(action.pressed, action.point, scope, context)
            for button, held in tuple(self.held.items()):
                if held.owner == scope and button in action.released:
                    del self.held[button]
            pending = tuple(self.held.values()) if self.closed else ()
        for held in pending:
            self._request_release(held)

    def matching_release(
        self,
        name: str,
        args: ToolArgs,
        context: ToolContext,
        conversation_id: str,
        attempt_id: str | None,
    ) -> HeldMouse | None:
        if name != "desktop_mouse" or args.get("action") != "up":
            return None
        from ...tools.desktop_mouse import BUTTONS

        with self._lock:
            held = self.held.get(BUTTONS.get(str(args.get("button", "left")), -1))
            return (
                held
                if (
                    held is not None
                    and held.owner == owner(context, conversation_id, attempt_id)
                    and BUTTONS.get(str(args.get("button", "left"))) == held.button
                )
                else None
            )

    def release(self, held: HeldMouse) -> ToolResult:
        from ...tools.desktop_mouse import release_owned_mouse

        result = release_owned_mouse(held.button, self.token, held.context)
        self._released(held, result)
        return result

    def _released(self, held: HeldMouse, result: ToolResult) -> None:
        with self._lock:
            changed = not result.ok and self._cleanup_errors.get(held.button) != result.output
            if result.ok and self.held.get(held.button) is held:
                del self.held[held.button]
                self._cleanup_errors.pop(held.button, None)
            elif not result.ok:
                self._cleanup_errors[held.button] = result.output
            self.cleanup_error = "; ".join(dict.fromkeys(self._cleanup_errors.values()))
        if changed:
            logging.getLogger(__name__).error("Sahipli fare temizliği başarısız: %s", result.output)
            if self.failure_reporter is not None:
                self.failure_reporter(result.output)

    def _request_release(self, held: HeldMouse) -> None:
        from ...tools.desktop_mouse import request_owned_release

        request_owned_release(
            held.button, self.token, held.context, lambda result: self._released(held, result)
        )

    def close(self) -> None:
        with self._lock:
            self.closed = True
            pending = tuple(self.held.values())
        for held in pending:
            self._request_release(held)

    def note_helper(
        self,
        capture: DesktopCapture,
        message: Message,
        context: ToolContext,
        conversation_id: str,
        attempt_id: str | None,
    ) -> None:
        if current_capture(context) is capture and message.ok and message.tool_call_id:
            self.pending.append(
                PendingObservation(capture, message, owner(context, conversation_id, attempt_id))
            )

    def for_request(
        self,
        messages: Sequence[Message],
        context: ToolContext,
        conversation_id: str,
        attempt_id: str | None,
    ) -> RequestObservation | None:
        capture = current_capture(context)
        scope = owner(context, conversation_id, attempt_id)
        self.pending[:] = [p for p in self.pending if p.capture is capture and p.owner == scope]
        if capture is None or context.cancelled.is_set():
            return None
        helper = any(p.message == message for p in self.pending for message in messages)
        direct = any(
            image_payload_digest(image) == capture.payload_digest
            for message in messages
            for image in message.images
            if image.isascii()
        )
        return RequestObservation(capture, scope, direct, helper) if direct or helper else None

    def acknowledge(
        self,
        observation: RequestObservation | None,
        *,
        usable: bool,
        images_supported: bool,
        context: ToolContext,
        conversation_id: str,
        attempt_id: str | None,
    ) -> None:
        self.acknowledged = (
            observation
            if usable
            and observation is not None
            and not context.cancelled.is_set()
            and observation.owner == owner(context, conversation_id, attempt_id)
            and current_capture(context) is observation.capture
            and (observation.helper or (observation.direct_image and images_supported))
            else None
        )

    def preflight(
        self,
        name: str,
        args: ToolArgs,
        context: ToolContext,
        conversation_id: str,
        attempt_id: str | None,
    ) -> str | None:
        with self._lock:
            if self.closed:
                return "Bu aktör turu kapandı; yeni fare eylemi başlatılmadı."
        points = coordinate_points(name, args)
        if points is None:
            return None
        capture = current_capture(context)
        observed = self.acknowledged
        if (
            context.cancelled.is_set()
            or capture is None
            or observed is None
            or observed.capture is not capture
            or observed.owner != owner(context, conversation_id, attempt_id)
        ):
            return GROUNDING_REQUIRED
        if capture.frame is None:
            return (
                "Koordinat kullanmadan önce tam desktop_screenshot al; "
                "yalnız kırpık görüntü yetmez."
            )
        left, top, width, height = capture.bounds
        if any(not (left <= x <= left + width and top <= y <= top + height) for x, y in points):
            return "Koordinat gözlenen ekran bölgesinin dışında; hedef bölgeyi önce incele."
        if not capture_file_matches(capture, context):
            return GROUNDING_REQUIRED
        with self._lock:
            if self.closed or context.cancelled.is_set():
                return GROUNDING_REQUIRED
        if current_capture(context) is not capture or self.acknowledged is not observed:
            return GROUNDING_REQUIRED
        return None


def capture_file_matches(capture: DesktopCapture, context: ToolContext) -> bool:
    """Bounded content check, only inside an already-authorized tool path."""
    try:
        path = resolve_path(context, str(capture.path))
        if path != capture.path:
            return False
        with path.open("rb") as stream:
            data = stream.read(capture.byte_size + 1)
    except (OSError, PathAccessError):
        return False
    return (
        len(data) == capture.byte_size and hashlib.sha256(data).hexdigest() == capture.file_digest
    )


def coordinate_points(name: str, args: ToolArgs) -> tuple[tuple[float, float], ...] | None:
    if name not in {"desktop_click", "desktop_mouse", "desktop_scroll"}:
        return None
    if name == "desktop_scroll" and "x" not in args and "y" not in args:
        return None

    def point(x: object, y: object) -> tuple[float, float] | None:
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            return None
        return float(x), float(y)

    start = point(args.get("x"), args.get("y"))
    if start is None:
        return None  # The original schema/tool still rejects malformed coordinates.
    if name == "desktop_mouse" and args.get("action") == "drag":
        end = point(args.get("to_x"), args.get("to_y"))
        return (start, end) if end is not None else (start,)
    return (start,)
