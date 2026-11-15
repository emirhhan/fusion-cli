"""Accepted current-tab authority, independent of persistent Chrome site grants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .chrome_devices import LOCAL_DEVICE_ID

if TYPE_CHECKING:
    from .chrome_bridge import ChromeBridge

SCOPE_VERSION = 1
BLOCKED = "Bu görev yalnız başlangıçtaki sekme ve site için yetkili; istenen işlem engellendi."
_RESTRICTED = re.compile(
    r"başka(?:\s+bir)?\s+(?:site|sekme|sayfa)(?:ye|ya|yi|yı)?\s+"
    r"(?:gitme|geçme|açma)|"
    r"(?:yalnızca|sadece|yalnız)\s+(?:bu|açık|mevcut|şu anki)\s+(?:sekme|site|sayfa)|"
    r"(?:only|just)\s+(?:the\s+)?(?:current|this)\s+(?:tab|site|page)|"
    r"(?:current|this)\s+(?:tab|site|page)\s+only|"
    r"(?:do not|don't|never)\s+(?:navigate|go)\s+to\s+(?:another|other|any other)\s+(?:site|page)",
    re.IGNORECASE,
)
READ_OPERATIONS = frozenset(
    {
        "tabs",
        "find",
        "snapshot",
        "assets",
        "text_page",
        "describe",
        "describe_key",
        "describe_at",
        "tree",
        "console",
        "network",
        "wait",
        "text",
        "design",
    }
)


def restricted_task(prompt: str) -> bool:
    return bool(_RESTRICTED.search(prompt))


def web_origin(value: object) -> str | None:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        suffix = (
            f":{port}"
            if port is not None and port != {"http": 80, "https": 443}[parsed.scheme]
            else ""
        )
        return f"{parsed.scheme}://{host}{suffix}"
    except (ValueError, UnicodeError):
        return None


@dataclass(frozen=True)
class ChromeTaskScope:
    tab_id: int
    origin: str
    device_id: str

    @classmethod
    def from_target(cls, target: object) -> ChromeTaskScope:
        if (
            not isinstance(target, dict)
            or type(target.get("scopeVersion")) is not int
            or target.get("scopeVersion") != SCOPE_VERSION
        ):
            raise ValueError("Bu görev için Fusion Chrome eklentisini yenileyip tekrar gönder.")
        tab_id = target.get("tabId")
        origin = web_origin(target.get("url"))
        if type(tab_id) is not int or tab_id <= 0 or origin is None:
            raise ValueError("Bu görev için başlangıçtaki açık http(s) sekmesi doğrulanamadı.")
        return cls(tab_id, origin, str(target.get("deviceId") or LOCAL_DEVICE_ID))

    def packet(self) -> dict[str, Any]:
        return {"version": SCOPE_VERSION, "tabId": self.tab_id, "origin": self.origin}

    def allows(self, operation: str, args: dict[str, Any]) -> bool:
        if "tabId" in args and args["tabId"] != self.tab_id:
            return False
        if operation in READ_OPERATIONS:
            return True
        if operation == "navigate":
            return web_origin(args.get("url")) == self.origin
        if operation == "tab_select":
            return args.get("id") == self.tab_id
        return operation == "history" and args.get("dir") == "reload"


class ScopedChromeBridge:
    """A per-job facade: neither other jobs nor bridge background tasks inherit it."""

    def __init__(self, bridge: ChromeBridge, scope: ChromeTaskScope) -> None:
        self._bridge = bridge
        self._scope = scope

    async def invoke(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self._scope.allows(operation, args):
            return {"ok": False, "hata": BLOCKED, "neden_kodu": "task_scope"}
        return await self._bridge.invoke(operation, args, task_scope=self._scope)

    def status(self) -> dict[str, Any]:
        return self._bridge.status()

    def element_name(self, ref: object) -> str | None:
        return self._bridge.element_name(ref)

    def browsers(self) -> list[dict[str, Any]]:
        return [b for b in self._bridge.browsers() if b["deviceId"] == self._scope.device_id]

    def select_browser(self, device_id: str) -> dict[str, Any] | None:
        return next((b for b in self.browsers() if b["deviceId"] == device_id), None)
