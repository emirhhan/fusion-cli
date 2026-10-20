"""Mobil uygulama RPC'leri: sohbet, proje, model, zamanlama, ek ve görsel.

Kapsam kontrolü `RemoteService`te, iş mantığı burada. Telefon yalnız bildirilen köklerde
(varsayılan kök ve masaüstünden gelen proje klasörleri) çalışabilir; keyfi dizin veremez.
"""

from __future__ import annotations

import asyncio
import base64
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ..core.protocols import Clock
from .backend import TaskBackend
from .navigation import NavigationHost
from .projects import ProjectError, ProjectStore
from .scopes import Scope
from .uploads import MediaReader, UploadError, UploadStore

CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
Method = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class MobileError(Exception):
    """Tipli RPC hatası: (kod, kullanıcıya gösterilebilir mesaj)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MobileApi:
    def __init__(
        self,
        *,
        backend: TaskBackend,
        projects: ProjectStore,
        uploads: UploadStore,
        media: MediaReader,
        clock: Clock,
        default_root: Path,
        session_lock: asyncio.Lock,
        navigation: NavigationHost | None = None,
    ) -> None:
        self._navigation = navigation
        self._backend = backend
        self._projects = projects
        self._uploads = uploads
        self._media = media
        self._clock = clock
        self._default_root = str(default_root.expanduser())
        self._lock = session_lock

    def _busy(self) -> None:
        if self._lock.locked():
            raise MobileError(
                "mesgul",
                "Bir görev çalışırken sohbet listesi/geçmişi açılamaz; bitince yeniden dene.",
            )

    def methods(self) -> dict[str, tuple[str, Method]]:
        read, run = Scope.PROJECT_READ.value, Scope.AGENT_RUN.value
        return {
            "desktop.targets": (Scope.DESKTOP_OBSERVE.value, self._desktop_targets),
            "desktop.focus": (run, self._desktop_focus),
            "projects.list": (read, self._projects_list),
            "projects.create": (run, self._projects_create),
            "projects.rename": (run, self._projects_rename),
            "projects.delete": (run, self._projects_delete),
            "chats.assign": (run, self._chats_assign),
            "chats.list": (read, self._chats_list),
            "chats.history": (read, self._chats_history),
            "models.list": (read, self._models_list),
            "models.select": (run, self._models_select),
            "schedules.list": (read, self._schedules_list),
            "schedules.enable": (run, self._schedules_enable),
            "uploads.put": (run, self._uploads_put),
            "media.get": (read, self._media_get),
        }

    async def _desktop_targets(self, _params: dict[str, Any]) -> dict[str, Any]:
        if self._navigation is None:
            raise MobileError("desteklenmiyor", "Masaüstü dock bağlantısı yok.")
        result = await self._navigation.list()
        if not result.get("ok"):
            raise MobileError(
                "hedef_yok",
                str(
                    result.get("native_error")
                    or result.get("chrome_error")
                    or "Açık hedefler alınamadı."
                ),
            )
        return dict(result)

    async def _desktop_focus(self, params: dict[str, Any]) -> dict[str, Any]:
        target = params.get("target")
        if self._navigation is None or not isinstance(target, dict):
            raise MobileError("gecersiz_istek", "Geçerli açık pencere veya sekme gerekli.")
        result = await self._navigation.focus(target)
        if not result.get("ok"):
            raise MobileError("hedef_yok", str(result.get("metin", "Hedef seçilemedi.")))
        return dict(result)

    # ---- tasks.create için yardımcılar ----
    def run_options(self, params: dict[str, Any]) -> dict[str, Any]:
        """`tasks.create` bağlamı: sohbet, proje kökü, model, ekler. Geçersizse `MobileError`."""
        options: dict[str, Any] = {}
        chat = params.get("chatId")
        if chat not in (None, ""):
            if not isinstance(chat, str) or not CHAT_ID.match(chat):
                raise MobileError("gecersiz_istek", "Sohbet kimliği geçersiz.")
            options["chat_id"] = chat
            project = params.get("projectId")
            if isinstance(project, str) and project:
                self._guard(self._projects.assign, chat, project)
        options["root"] = self.root_for(params.get("root"), chat if isinstance(chat, str) else "")
        if isinstance(params.get("tier"), str) and params["tier"]:
            options["tier"] = params["tier"]
        ids = params.get("attachments")
        if isinstance(ids, list) and ids:
            try:
                options["attachments"] = self._uploads.resolve(ids)
            except UploadError as error:
                raise MobileError("ek_yok", str(error)) from error
        return options

    def root_for(self, requested: object, chat_id: str = "") -> str:
        """İstenen kök yalnız bilinen köklerden olabilir; yoksa projenin ya da varsayılan kök."""
        known = {self._default_root, *self._projects.known_roots()}
        if isinstance(requested, str) and requested:
            if requested not in known:
                raise MobileError("kok_izinsiz", "Bu klasör uzaktan kullanılamaz.")
            return requested
        project = self._projects.chats().get(chat_id)
        record = self._projects.get(project) if project else None
        return str(record["root"]) if record and "root" in record else self._default_root

    async def find_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        listed = await self._backend.call("zamanlama.liste", {})
        for item in listed.get("gorevler", []):
            if item.get("id") == schedule_id:
                return dict(item)
        return None

    @staticmethod
    def _guard(function: Callable[..., Any], *args: Any) -> Any:  # noqa: ANN401
        try:
            return function(*args)
        except ProjectError as error:
            raise MobileError("proje_hata", str(error)) from error

    # ---- projeler ----
    async def _projects_list(self, _p: dict[str, Any]) -> dict[str, Any]:
        return {
            "projects": [
                {**item, "hasFolder": "root" in item} for item in self._projects.list_projects()
            ],
            "chatProjects": self._projects.chats(),
        }

    async def _projects_create(self, p: dict[str, Any]) -> dict[str, Any]:
        record = self._guard(self._projects.create, str(p.get("name", "")), self._clock.now())
        return {"project": record}

    async def _projects_rename(self, p: dict[str, Any]) -> dict[str, Any]:
        record = self._guard(
            self._projects.rename, str(p.get("projectId", "")), str(p.get("name", ""))
        )
        return {"project": record}

    async def _projects_delete(self, p: dict[str, Any]) -> dict[str, Any]:
        self._guard(self._projects.delete, str(p.get("projectId", "")))
        return {"deleted": True}

    async def _chats_assign(self, p: dict[str, Any]) -> dict[str, Any]:
        project = p.get("projectId")
        self._guard(self._projects.assign, str(p.get("chatId", "")), project if project else None)
        return {"assigned": True}

    # ---- sohbetler ----
    async def _chats_list(self, _p: dict[str, Any]) -> dict[str, Any]:
        roots = [self._default_root, *sorted(self._projects.known_roots() - {self._default_root})]
        mapping = self._projects.chats()
        self._busy()
        chats: list[dict[str, Any]] = []
        async with self._lock:
            for root in roots:
                await self._backend.call("oturum.baslat", {"kok": root})
                listed = await self._backend.call("sohbet.listele", {})
                for item in listed.get("sohbetler", []):
                    chat_id = str(item.get("sohbet_id", ""))
                    chats.append(
                        {
                            "id": chat_id,
                            "title": str(item.get("baslik", "")),
                            "updatedAt": item.get("guncelleme", 0),
                            "messageCount": item.get("mesaj_sayisi", 0),
                            "root": root,
                            "projectId": mapping.get(chat_id),
                        }
                    )
        chats.sort(key=lambda c: c["updatedAt"] or 0, reverse=True)
        return {"chats": chats}

    async def _chats_history(self, p: dict[str, Any]) -> dict[str, Any]:
        chat_id = str(p.get("chatId", ""))
        if not CHAT_ID.match(chat_id):
            raise MobileError("gecersiz_istek", "Sohbet kimliği geçersiz.")
        root = self.root_for(p.get("root"), chat_id)
        self._busy()
        async with self._lock:
            await self._backend.call("oturum.baslat", {"kok": root, "sohbet_id": chat_id})
            history = await self._backend.call("oturum.gecmis", {})
        messages = [
            {
                "role": "user" if m.get("rol") == "kullanici" else "assistant",
                "text": str(m.get("metin", "")),
                "id": m.get("id", ""),
            }
            for m in history.get("mesajlar", [])
        ]
        return {"chatId": chat_id, "messages": messages}

    # ---- model (kademe) ----
    async def _models_list(self, _p: dict[str, Any]) -> dict[str, Any]:
        listed = await self._backend.call("kademe.listele", {})
        if not listed.get("ok"):
            raise MobileError("model_yok", str(listed.get("metin", "Model listesi yok.")))
        return {
            "tiers": [
                {"name": t["ad"], "label": t.get("etiket", t["ad"]), "model": t.get("model", "")}
                for t in listed.get("kademeler", [])
            ],
            "active": listed.get("etkin"),
            "editable": bool(listed.get("duzenlenebilir")),
        }

    async def _models_select(self, p: dict[str, Any]) -> dict[str, Any]:
        result = await self._backend.call("kademe.sec", {"ad": str(p.get("name", ""))})
        if not result.get("ok"):
            raise MobileError("model_hata", str(result.get("metin", "Model seçilemedi.")))
        return {"selected": str(p.get("name", "")), "message": str(result.get("metin", ""))}

    # ---- zamanlananlar ----
    async def _schedules_list(self, _p: dict[str, Any]) -> dict[str, Any]:
        listed = await self._backend.call("zamanlama.liste", {})
        if not listed.get("ok"):
            raise MobileError("zamanlama_hata", str(listed.get("metin", "Zamanlama okunamadı.")))
        return {
            "schedules": [
                {
                    "id": item.get("id"),
                    "title": item.get("baslik", ""),
                    "task": item.get("gorev", ""),
                    "enabled": item.get("etkin") is not False,
                    "next": item.get("sonraki"),
                    "last": item.get("son_calisma"),
                    "kind": item.get("tur", ""),
                }
                for item in listed.get("gorevler", [])
            ]
        }

    async def _schedules_enable(self, p: dict[str, Any]) -> dict[str, Any]:
        result = await self._backend.call(
            "zamanlama.etkin", {"id": p.get("id"), "etkin": p.get("enabled") is True}
        )
        if not result.get("ok"):
            raise MobileError("zamanlama_hata", str(result.get("metin", "Güncellenemedi.")))
        return {"updated": True}

    # ---- ek ve görsel ----
    async def _uploads_put(self, p: dict[str, Any]) -> dict[str, Any]:
        try:
            info = self._uploads.put(
                str(p.get("name", "ek")), str(p.get("kind", "file")), str(p.get("dataBase64", ""))
            )
        except UploadError as error:
            raise MobileError("ek_hata", str(error)) from error
        return dict(info)

    async def _media_get(self, p: dict[str, Any]) -> dict[str, Any]:
        try:
            media_type, data = await asyncio.to_thread(self._media.read, str(p.get("path", "")))
        except UploadError as error:
            raise MobileError("gorsel_hata", str(error)) from error
        return {"mediaType": media_type, "dataBase64": base64.b64encode(data).decode("ascii")}
