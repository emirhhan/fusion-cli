"""Fusion → Kits gelen kutusu: bir Kit'e mesaj/görev bırakan ve durumunu okuyan araçlar.

Kits ayrı bir Node sürecidir (`fusion-kits`); Fusion onu masaüstünde yan süreç olarak
başlatır. Bu modül Kits'in yerel HTTP uçlarına (`/api/kits…`) konuşur. Adres iki yoldan
bulunur: masaüstünün başlattığı Kits `kits-bridge.json` durum dosyasına adres+pid yazar
(pid ölüyse dosya yok sayılır); dosya yoksa elle başlatılmış Kits için varsayılan
`KITS_DEFAULT_URL` denenir. Teslim makbuzu "kuyruğa alındı" demektir, "yapıldı" değil:
Kit işi kendi sırası gelince kendi sohbetinde yapar, sonucu `kit_task_status` okur.

Ölçüldü (31 Ekim): Fusion→Kit yönünde yalnız zamanlanmış teslim (postMessage) vardı;
CLI'dan ya da ajandan bir Kit'e serbest mesaj bırakma yolu yoktu (P-063).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from ..config.paths import kits_state_file
from ..core.constants import KITS_DEFAULT_URL, KITS_TIMEOUT_S
from ..core.errors import FusionError
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str

#: Gönderilebilecek metnin sınırları (Kits `inboxSchema` ile aynı).
MIN_TEXT_CHARS = 3
MAX_TEXT_CHARS = 4000
MAX_TITLE_CHARS = 120
#: Türkçe tür adı → Kits API türü.
KINDS = {"gorev": "task", "mesaj": "message", "task": "task", "message": "message"}
#: Kits'ten gelen ham JSON yükü; şeması Kits'e aittir ve alan alan okunur.
JsonPayload = dict[str, Any] | list[Any]
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


class KitsError(FusionError):
    """Kits'e ulaşılamadı ya da Kits isteği reddetti; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True, slots=True)
class KitsEndpoint:
    """Kits'in bulunduğu adres ve nereden öğrenildiği (`masaustu` | `varsayilan`)."""

    url: str
    source: str


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_kits_state(path: Path) -> KitsEndpoint | None:
    """Durum dosyasını oku; yazan süreç ölmüşse ya da adres yerel HTTP değilse `None`."""
    try:
        veri = json.loads(path.read_text(encoding="utf-8"))
        url = str(veri["url"])
        pid = int(veri["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK_HOSTS or not parts.port:
        return None
    if not _pid_alive(pid):
        return None
    return KitsEndpoint(f"{parts.scheme}://{parts.netloc}", "masaustu")


def resolve_kits_endpoint(
    state_file: Path | None = None, *, default_url: str = KITS_DEFAULT_URL
) -> KitsEndpoint:
    """Masaüstünün duyurduğu adres; yoksa elle başlatılmış Kits varsayılanı."""
    found = read_kits_state(state_file or kits_state_file())
    return found or KitsEndpoint(default_url, "varsayilan")


def _unreachable_message(endpoint: KitsEndpoint) -> str:
    if endpoint.source == "masaustu":
        return (
            f"Kits'e ulaşılamadı ({endpoint.url}). Fusion masaüstünde Kits bölümünü açıp "
            "yeniden dene."
        )
    return (
        f"Kits çalışmıyor ({endpoint.url}). Fusion masaüstünde Kits bölümünü aç ya da "
        "fusion-kits klasöründe `npm run kits:start` çalıştır."
    )


class KitsClient:
    """Kits gelen kutusu uçlarına yerel HTTP istemcisi (yalnız 127.0.0.1)."""

    def __init__(
        self,
        endpoint: KitsEndpoint | None = None,
        *,
        timeout_s: float = KITS_TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint or resolve_kits_endpoint()
        self._timeout_s = timeout_s
        self._transport = transport

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> JsonPayload:
        try:
            async with httpx.AsyncClient(
                base_url=self.endpoint.url, timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.request(method, path, json=body)
        except httpx.HTTPError as error:
            raise KitsError(_unreachable_message(self.endpoint)) from error
        try:
            parsed = response.json()
        except ValueError:
            parsed = {}
        payload: JsonPayload = parsed if isinstance(parsed, dict | list) else {}
        if response.status_code >= 400:
            hata = payload.get("error") if isinstance(payload, dict) else None
            raise KitsError(
                str(hata) if hata else f"Kits isteği başarısız oldu (HTTP {response.status_code})."
            )
        return payload

    async def list_kits(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/kits")
        kits = payload.get("kits") if isinstance(payload, dict) else None
        return [kit for kit in kits if isinstance(kit, dict)] if isinstance(kits, list) else []

    async def send(
        self, kit: str, text: str, *, title: str | None = None, kind: str = "gorev"
    ) -> dict[str, Any]:
        """Kit'e mesaj/görev bırak; makbuz `{taskId, threadId, status: "queued"}` döner."""
        body: dict[str, Any] = {"text": text, "kind": KINDS.get(kind, "task")}
        if title:
            body["title"] = title[:MAX_TITLE_CHARS]
        receipt = await self._request("POST", f"/api/kits/{quote(kit, safe='')}/inbox", body)
        return receipt if isinstance(receipt, dict) else {}

    async def inbox(self, kit: str) -> list[dict[str, Any]]:
        payload = await self._request("GET", f"/api/kits/{quote(kit, safe='')}/inbox")
        items = payload.get("items") if isinstance(payload, dict) else None
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    async def status(self, kit: str, task_id: str) -> dict[str, Any]:
        payload = await self._request(
            "GET", f"/api/kits/{quote(kit, safe='')}/inbox/{quote(task_id, safe='')}"
        )
        return payload if isinstance(payload, dict) else {}


def validate_text(text: str) -> str | None:
    """Gönderilecek metnin Türkçe hata nedeni; geçerliyse `None`."""
    if len(text.strip()) < MIN_TEXT_CHARS:
        return f"Metin en az {MIN_TEXT_CHARS} karakter olmalı."
    if len(text) > MAX_TEXT_CHARS:
        return f"Metin en fazla {MAX_TEXT_CHARS} karakter olabilir."
    return None


def _client(context: ToolContext) -> KitsClient:
    # Testler ve masaüstü oturumu `kits` özniteliğiyle hazır istemci verebilir.
    injected = getattr(context, "kits", None)
    return injected if isinstance(injected, KitsClient) else KitsClient()


def _ok(veri: JsonPayload) -> ToolResult:
    return ToolResult(json.dumps(veri, ensure_ascii=False))


async def kits_list(_args: ToolArgs, context: ToolContext) -> ToolResult:
    """Kits'teki Kit'leri listele (kimlik, ad, Fusion izni, gelen kutusu sohbeti)."""
    try:
        kits = await _client(context).list_kits()
    except KitsError as error:
        return ToolResult.failure(str(error))
    if not kits:
        return ToolResult("Kits'te hiç Kit yok; Fusion ana menüsünden Kits bölümünde bir Kit ekle.")
    return _ok(
        [
            {
                "id": kit.get("id"),
                "ad": kit.get("name"),
                "fusion_izni": bool(kit.get("fusionAllowed")),
                "gelen_kutusu": kit.get("inboxThreadId"),
            }
            for kit in kits
        ]
    )


async def kit_send(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir Kit'e mesaj ya da görev bırak; makbuz kuyruğa alındığını söyler."""
    kit = require_str(args, "kit")
    text = require_str(args, "text")
    reason = validate_text(text)
    if reason is not None:
        return ToolResult.failure(reason)
    title = args.get("title")
    kind = args.get("kind")
    try:
        receipt = await _client(context).send(
            kit,
            text,
            title=title if isinstance(title, str) and title.strip() else None,
            kind=kind if isinstance(kind, str) else "gorev",
        )
    except KitsError as error:
        return ToolResult.failure(str(error))
    return _ok(
        {
            "durum": "kuyrukta",
            "kit": receipt.get("kitId"),
            "gorev_id": receipt.get("taskId"),
            "sohbet": receipt.get("threadId"),
            "not": (
                "Kit işi kendi sırası gelince yapar; sonucu kit_task_status ile oku. "
                "Bu makbuz işin bittiği anlamına gelmez."
            ),
        }
    )


async def kit_task_status(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Gelen kutusundaki bir görevin durumunu ve sonucunu oku; görev verilmezse listeyi."""
    kit = require_str(args, "kit")
    task_id = args.get("task_id")
    try:
        client = _client(context)
        if isinstance(task_id, str) and task_id.strip():
            return _ok(await client.status(kit, task_id.strip()))
        return _ok(await client.inbox(kit))
    except KitsError as error:
        return ToolResult.failure(str(error))
