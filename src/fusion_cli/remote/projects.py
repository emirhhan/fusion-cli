"""Uzaktan görünen proje kaydı: ad, isteğe bağlı klasör ve sohbet → proje eşlemesi.

Masaüstü uygulamasının kaydı (`fusion.projects.v1`) WebView deposundadır ve çekirdek onu okuyamaz.
Bu depo aynı şekli taşır; masaüstü `uzak.projeler_esitle` ile gönderince telefon aynı
projeleri görür.
Telefon klasör SEÇEMEZ: projenin klasörü yalnız masaüstünden gelir, telefondan açılan projeler
klasörsüzdür (varsayılan kökte çalışır). Böylece uzaktan işin çalışacağı dizin genişletilemez.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

PROJECT_NAME_MAX = 80


class ProjectError(ValueError):
    """Kullanıcıya gösterilebilir proje hatası."""


def _same(left: str, right: str) -> bool:
    return left.casefold() == right.casefold()


class ProjectStore:
    """Proje ve sohbet eşlemesi; her yazma kalıcıdır (yalnız sahibine açık dosya)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._projects: list[dict[str, Any]] = []
        self._chats: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            self.replace(raw.get("projects"), raw.get("chats"), persist=False)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(json.dumps({"projects": self._projects, "chats": self._chats}), "utf-8")
        temp.chmod(0o600)
        temp.replace(self._path)

    def replace(self, projects: object, chats: object, *, persist: bool = True) -> None:
        """Masaüstü kaydını olduğu gibi al; bozuk kayıtlar atılır, geri kalan korunur."""
        clean: list[dict[str, Any]] = []
        for item in projects if isinstance(projects, list) else []:
            if not isinstance(item, dict):
                continue
            ident, name = item.get("id"), item.get("name")
            if not isinstance(ident, str) or not isinstance(name, str) or not name.strip():
                continue
            record: dict[str, Any] = {
                "id": ident,
                "name": name.strip()[:PROJECT_NAME_MAX],
                "createdAt": item.get("createdAt", 0),
            }
            if isinstance(item.get("root"), str) and item["root"].strip():
                record["root"] = item["root"].strip()
            clean.append(record)
        known = {item["id"] for item in clean}
        mapping = {
            chat: project
            for chat, project in (chats if isinstance(chats, dict) else {}).items()
            if isinstance(chat, str) and isinstance(project, str) and project in known
        }
        self._projects, self._chats = clean, mapping
        if persist:
            self._save()

    def list_projects(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._projects]

    def chats(self) -> dict[str, str]:
        return dict(self._chats)

    def get(self, project_id: str) -> dict[str, Any] | None:
        return next((dict(p) for p in self._projects if p["id"] == project_id), None)

    def known_roots(self) -> set[str]:
        return {p["root"] for p in self._projects if "root" in p}

    def create(self, name: str, now: float) -> dict[str, Any]:
        clean = self._clean_name(name)
        record = {"id": "p_" + uuid.uuid4().hex[:12], "name": clean, "createdAt": now}
        self._projects.append(record)
        self._save()
        return dict(record)

    def rename(self, project_id: str, name: str) -> dict[str, Any]:
        clean = self._clean_name(name, own=project_id)
        for index, item in enumerate(self._projects):
            if item["id"] == project_id:
                self._projects[index] = {**item, "name": clean}
                self._save()
                return dict(self._projects[index])
        raise ProjectError("Proje bulunamadı.")

    def delete(self, project_id: str) -> None:
        """Projeyi siler; sohbetler silinmez, "Sohbetler"e (projesiz) döner."""
        if self.get(project_id) is None:
            raise ProjectError("Proje bulunamadı.")
        self._projects = [p for p in self._projects if p["id"] != project_id]
        self._chats = {c: p for c, p in self._chats.items() if p != project_id}
        self._save()

    def assign(self, chat_id: str, project_id: str | None) -> None:
        if not chat_id:
            raise ProjectError("Sohbet kimliği gerekli.")
        if project_id is None:
            self._chats.pop(chat_id, None)
        elif self.get(project_id) is None:
            raise ProjectError("Proje bulunamadı.")
        else:
            self._chats[chat_id] = project_id
        self._save()

    def _clean_name(self, name: str, own: str | None = None) -> str:
        clean = name.strip()
        if not clean:
            raise ProjectError("Proje adı boş olamaz.")
        if len(clean) > PROJECT_NAME_MAX:
            raise ProjectError(f"Proje adı en fazla {PROJECT_NAME_MAX} karakter olabilir.")
        if any(p["id"] != own and _same(p["name"], clean) for p in self._projects):
            raise ProjectError("Bu adla bir proje zaten var.")
        return clean
