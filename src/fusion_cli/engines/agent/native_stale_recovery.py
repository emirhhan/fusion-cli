"""Method feedback for repeatedly rejected native AX targets; never action authority."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from ...core.events import ToolOutcome
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools import desktop, desktop_background, desktop_inspect, desktop_mouse
from ...tools.args import coerce_int

_Scope = tuple[int, int]
_Target = tuple[int, int, str]
_CauseTarget = tuple[int, int, str, str]
_CAUSE_ADVICE = {
    "permission_required": (
        "Erişilebilirlik izni yok. Aynı çağrıyı tekrarlama; kullanıcı izni düzeltene kadar "
        "yerel eyleme geçme."
    ),
    "window_missing": (
        "Hedef pencere kapandı veya kimliği değişti. Güncel PID ve pencere kimliğini "
        "yeniden doğrulamadan eyleme geçme."
    ),
    "window_unverified": (
        "Pencerenin AX kimliği doğrulanamadı. Hedefi yeniden doğrulamadan eyleme geçme; "
        "koordinat yöntemi bu engeli kaldırmaz."
    ),
    "tree_incomplete": (
        "AX ağacı tamamlanamadı. Benzersiz ve güncel hedef doğrulanmadan eyleme geçme."
    ),
    "identity_ambiguous": (
        "AX öğesinin kimliği tekil değil. Yeni ref tekillik sağlamaz; benzersiz hedef "
        "doğrulanmadan eyleme geçme."
    ),
    "path_changed": (
        "AX öğesinin yolu kimliğiyle uyuşmuyor. Güncel inceleme ve benzersiz hedef "
        "doğrulaması gerekli."
    ),
    "press_unsupported": (
        "Öğe AXPress desteklemiyor. Aynı eylemi başka ref ile tekrarlama. Alternatif "
        "yöntem için hedefi ve mevcut izinleri ayrıca doğrula."
    ),
    "value_unsupported": (
        "Öğe AXValue yazmayı desteklemiyor. Aynı eylemi başka ref ile tekrarlama. "
        "Alternatif yöntem için hedefi ve mevcut izinleri ayrıca doğrula."
    ),
    "value_unverified": (
        "Yazma sonucu doğrulanamadı; işlem uygulanmış olabilir. Aynı yazmayı tekrarlama; "
        "önce salt okunur gözlemle sonucu doğrula."
    ),
    "action_rejected": (
        "AX işlemi başarısız döndü. Sonuç doğrulanmadan aynı eylemi tekrarlama; "
        "önce salt okunur gözlem yap."
    ),
    "unknown": (
        "Yerel başarısızlığın nedeni doğrulanamadı. Sonucu salt okunur gözlemle kontrol et; "
        "aynı eylemi veya koordinat yöntemini körlemesine deneme."
    ),
    "stale_tree": "",
}


def is_native_recovery_observation(tool: Tool | None, *, remote: bool) -> bool:
    return (
        not remote
        and tool is not None
        and tool.run is desktop_background.desktop_background_inspect
    )


_FOREGROUND_INPUTS = (
    desktop.desktop_key,
    desktop.desktop_type,
    desktop_mouse.desktop_click,
    desktop_mouse.desktop_scroll,
)


def is_native_mutation(tool: Tool | None, *, remote: bool) -> bool:
    """Trusted native input failures are not failed source-file edits."""
    return (
        tool is not None
        and tool.mutating
        and not remote
        and any(
            tool.run is run
            for run in (
                *_FOREGROUND_INPUTS,
                desktop_mouse.desktop_mouse,
                desktop_background.desktop_background_action,
                desktop_inspect.desktop_window_focus,
            )
        )
    )


@dataclass(frozen=True, slots=True)
class NativeRecoveryInvocation:
    """Internal dispatched-input receipt for feedback only; never authorization."""

    tool: Tool
    arguments: ToolArgs


def _positive(value: object) -> bool:
    return type(value) is int and 0 < value < 2**32


def _target(args: ToolArgs) -> _Target | None:
    pid, window, action, ref = (
        args.get("pid"),
        args.get("window_id"),
        args.get("action"),
        args.get("ref"),
    )
    if (
        not _positive(pid)
        or not _positive(window)
        or not isinstance(action, str)
        or action not in ("press", "set_value")
    ):
        return None
    if not isinstance(ref, str) or not ref or len(ref) > 50_000:
        return None
    try:
        payload = json.loads(base64.b64decode(ref, validate=True))
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(payload, dict):
        return None
    if type(payload.get("pid")) is not int or type(payload.get("id")) is not int:
        return None
    if payload["pid"] != pid or payload["id"] != window:
        return None
    identity, path, fingerprint = (
        payload.get("identity"),
        payload.get("path"),
        payload.get("fingerprint"),
    )
    if (
        not isinstance(identity, str)
        or not identity.startswith("AX")
        or "\x1f" not in identity
        or len(identity) > 4096
        or not isinstance(path, list)
        or len(path) > 64
        or any(type(index) is not int or index < 0 for index in path)
        or not isinstance(fingerprint, str)
        or not fingerprint
        or len(fingerprint) > 128
    ):
        return None
    value = args.get("value", "") if action == "set_value" else ""
    if not isinstance(value, str) or len(value) > 10_000:
        return None
    # Only an opaque digest is retained. Diagnostic counters, path shifts and
    # fingerprint nonces are not a new interaction method for a unique identity.
    digest = hashlib.sha256(json.dumps([identity, action, value]).encode()).hexdigest()
    return payload["pid"], payload["id"], digest


def _stale_guard(result: ToolResult) -> bool:
    payload = result.structured
    if not isinstance(payload, Mapping) or payload.get("ok") is not False:
        return False
    checks = payload.get("action_checks")
    return isinstance(checks, Mapping) and (
        checks.get("tree_complete") is True
        and checks.get("fingerprint_matches") is False
        and checks.get("identity_unique") is True
        and type(checks.get("path_identity_matches")) is bool
    )


@dataclass(slots=True)
class NativeStaleRecovery:
    """Per-drive rejected-target episodes; observations do not erase an episode."""

    _failures: dict[_Target, int] = field(default_factory=dict)
    max_targets: int = 256
    _causes: dict[_CauseTarget, tuple[int, int]] = field(default_factory=dict)

    def cause_summary(self) -> tuple[dict[str, object], ...]:
        """Bounded trusted attempts/native-boundary time; never success evidence."""
        return tuple(
            {
                "pid": key[0],
                "window_id": key[1],
                "operation": key[2],
                "cause": key[3],
                "attempts": value[0],
                "native_elapsed_ms": value[1],
            }
            for key, value in self._causes.items()
        )

    def failure_note(
        self,
        tool: Tool | None,
        args: ToolArgs,
        result: ToolResult,
        outcome: ToolOutcome,
        *,
        remote: bool,
    ) -> str | None:
        if (
            remote
            or tool is None
            or outcome is not ToolOutcome.FAILED
            or tool.run
            not in (
                desktop_background.desktop_background_action,
                desktop_background.desktop_background_inspect,
            )
        ):
            return None
        payload = (result.structured or {}).get("native_failure")
        if not isinstance(payload, Mapping):
            return None
        pid, window = coerce_int(args.get("pid")), coerce_int(args.get("window_id"))
        operation = (
            "action" if tool.run is desktop_background.desktop_background_action else "inspect"
        )
        cause, elapsed = payload.get("cause"), payload.get("elapsed_ms")
        if (
            not _positive(pid)
            or not _positive(window)
            or type(payload.get("pid")) is not int
            or type(payload.get("window_id")) is not int
            or payload.get("pid") != pid
            or payload.get("window_id") != window
            or payload.get("operation") != operation
            or not isinstance(cause, str)
            or cause not in _CAUSE_ADVICE
            or type(elapsed) is not int
            or not 0 <= elapsed <= 600_000
        ):
            return None
        assert isinstance(pid, int) and isinstance(window, int)
        key = (pid, window, operation, cause)
        if key not in self._causes and len(self._causes) >= max(1, self.max_targets):
            del self._causes[next(iter(self._causes))]
        count, total = self._causes.get(key, (0, 0))
        self._causes[key] = (count + 1, total + elapsed)
        if cause == "stale_tree":
            return None
        return "FUSION_AX: " + _CAUSE_ADVICE[cause] + " Bu bilgi izin veya eylem yetkisi vermez."

    def _clear_window(self, scope: _Scope) -> None:
        for key in tuple(self._failures):
            if key[:2] == scope:
                del self._failures[key]

    def observe(
        self,
        tool: Tool | None,
        args: ToolArgs,
        result: ToolResult,
        outcome: ToolOutcome,
        context: ToolContext,
        *,
        remote: bool,
    ) -> int | None:
        """Return a recognized stale episode's count, not permission or execution evidence."""
        if tool is None or remote:
            return None
        if tool.run is desktop_background.desktop_background_action:
            target = _target(args)
            if target is None:
                return None
            if outcome is ToolOutcome.OK and not result.is_observation:
                self._clear_window(target[:2])
            elif outcome is ToolOutcome.FAILED and _stale_guard(result):
                if target not in self._failures and len(self._failures) >= max(1, self.max_targets):
                    del self._failures[next(iter(self._failures))]
                count = self._failures.get(target, 0) + 1
                self._failures[target] = count
                return count
        elif (
            outcome is ToolOutcome.OK
            and not result.is_observation
            and any(tool.run is run for run in _FOREGROUND_INPUTS)
        ):
            focused = context.desktop.focused_window
            window = context.desktop.focused_window_id
            if focused is not None and _positive(focused[0]) and _positive(window):
                self._clear_window((focused[0], window))
        return None


def recovery_note(count: int, available: Collection[str]) -> str:
    """Fixed model-only advice; neither native payload nor target labels are instructions."""
    note = (
        f"FUSION_NOT: Aynı AX hedefindeki aynı eylem {count} kez eski ağaç korumasına "
        "takıldı. Yeni ref veya fingerprint bu hedef için yeni bir yöntem değildir; "
        "yeniden incele/aynı eylemi dene döngüsünü bırak ve yeni bir yöntem seç."
    )
    keyboard = [name for name in ("desktop_key", "desktop_type") if name in available]
    if keyboard:
        note += " Uygun klavye etkileşimi için " + " / ".join(keyboard) + " araçlarını değerlendir."
    if "view_image" in available:
        note += " Görsel yöntem gerekiyorsa güncel görüntüyü önce view_image ile incele."
    return note + " Her yöntemin mevcut izinleri ve hedef doğrulamaları aynen geçerlidir."
