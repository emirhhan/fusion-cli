"""Masaüstü uygulaması için proje-kökü sınırlı salt-okunur çalışma alanı.

Bu katman UI'ın dosya sistemine doğrudan erişmesini engeller. Bütün yollar tek
bir sınır fonksiyonundan geçer; sembolik bağlar dahil gerçek hedef proje
kökünün dışına çıkamaz.
"""

from __future__ import annotations

import difflib
import hashlib
import mimetypes
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 200
_DEFAULT_MAX_BYTES = 256 * 1024
_MAX_READ_BYTES = 2 * 1024 * 1024
_OUTSIDE = "Proje klasörünün dışına çıkılamaz."


class WorkspacePathError(ValueError):
    """Kullanıcı yolu proje sınırını ihlal etti."""


@dataclass(frozen=True)
class UndoEntry:
    path: str
    existed: bool
    before: bytes
    after: bytes
    diff: str
    added: int
    removed: int


class WorkspaceJournal:
    """Bir uygulama oturumundaki doğrudan UI yazımlarının sınırlı günlüğü."""

    def __init__(self, *, max_entries: int = 20, max_bytes: int = 8 * 1024 * 1024) -> None:
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._entries: list[UndoEntry] = []
        self._bytes = 0

    def record(self, entry: UndoEntry) -> None:
        self._entries.append(entry)
        self._bytes += len(entry.before) + len(entry.after)
        while self._entries and (
            len(self._entries) > self._max_entries or self._bytes > self._max_bytes
        ):
            removed = self._entries.pop(0)
            self._bytes -= len(removed.before) + len(removed.after)

    def latest(self) -> list[UndoEntry]:
        by_path: dict[str, UndoEntry] = {}
        for entry in self._entries:
            by_path[entry.path] = entry
        return list(by_path.values())

    def pop(self, path: str) -> UndoEntry | None:
        for index in range(len(self._entries) - 1, -1, -1):
            entry = self._entries[index]
            if entry.path == path:
                self._entries.pop(index)
                self._bytes -= len(entry.before) + len(entry.after)
                return entry
        return None

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "metin": message}


def _integer(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _resolve_inside(root: Path, raw: object) -> Path:
    """`raw` yolunu çözer; sözcüksel ve symlink kaçışlarını reddeder."""
    root = root.resolve()
    text = str(raw or "")
    relative = PurePath(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkspacePathError(_OUTSIDE)
    candidate = (root / text).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise WorkspacePathError(_OUTSIDE)
    return candidate


def _relative(root: Path, path: Path) -> str:
    value = path.relative_to(root.resolve()).as_posix()
    return "" if value == "." else value


def workspace_status(root: Path) -> dict[str, Any]:
    resolved = root.resolve()
    return {
        "ok": True,
        "kok": str(resolved),
        "git": (resolved / ".git").exists(),
        "okunabilir": os.access(resolved, os.R_OK),
        "yazilabilir": os.access(resolved, os.W_OK),
    }


def list_entries(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        directory = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    if not directory.exists():
        return _error("Klasör bulunamadı.")
    if not directory.is_dir():
        return _error("Seçilen yol bir klasör değil.")

    limit = _integer(data.get("limit"), default=_DEFAULT_LIMIT, minimum=1, maximum=_MAX_LIMIT)
    cursor = _integer(data.get("cursor"), default=0, minimum=0, maximum=2**31 - 1)
    try:
        entries = sorted(
            directory.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.casefold(), item.name),
        )
    except OSError:
        return _error("Klasör okunamadı.")

    page = entries[cursor : cursor + limit]
    payload: list[dict[str, Any]] = []
    for entry in page:
        try:
            stat = entry.stat()
            kind = "klasor" if entry.is_dir() else "dosya"
            payload.append(
                {
                    "ad": entry.name,
                    "yol": _relative(root, entry),
                    "tur": kind,
                    "boyut": 0 if kind == "klasor" else stat.st_size,
                    "degistirilme": stat.st_mtime,
                }
            )
        except OSError:
            continue
    next_cursor = cursor + len(page)
    has_more = next_cursor < len(entries)
    return {
        "ok": True,
        "yol": _relative(root, directory),
        "girdiler": payload,
        "next_cursor": next_cursor if has_more else None,
        "has_more": has_more,
    }


def _mime(path: Path, *, binary: bool) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    return "application/octet-stream" if binary else "text/plain"


def read_entry(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        path = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    if not path.exists():
        return _error("Dosya bulunamadı.")
    if not path.is_file():
        return _error("Seçilen yol bir dosya değil.")

    max_bytes = _integer(
        data.get("max_bytes"),
        default=_DEFAULT_MAX_BYTES,
        minimum=1,
        maximum=_MAX_READ_BYTES,
    )
    try:
        raw = path.read_bytes()
    except OSError:
        return _error("Dosya okunamadı.")
    digest = hashlib.sha256(raw).hexdigest()
    sample = raw[:max_bytes]
    binary = b"\x00" in sample
    text: str | None = None
    if not binary:
        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            binary = True
    return {
        "ok": True,
        "yol": _relative(root, path),
        "tur": "binary" if binary else "metin",
        "mime": _mime(path, binary=binary),
        "boyut": len(raw),
        "sha256": digest,
        "icerik": None if binary else text,
        "kesildi": len(raw) > max_bytes,
    }


def _diff(path: str, before: bytes, after: bytes) -> tuple[str, int, int]:
    old = before.decode("utf-8").splitlines(keepends=True)
    new = after.decode("utf-8").splitlines(keepends=True)
    lines = list(
        difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
    )
    body = "\n".join(line.rstrip("\n") for line in lines)
    added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return body, added, removed


def _atomic_write(path: Path, content: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_entry(
    root: Path,
    data: dict[str, Any],
    journal: WorkspaceJournal,
) -> dict[str, Any]:
    try:
        path = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    content = data.get("icerik")
    expected = data.get("expected_sha256")
    if not isinstance(content, str) or not isinstance(expected, str):
        return _error("Dosya içeriği ve beklenen sürüm zorunludur.")
    if path.exists() and not path.is_file():
        return _error("Seçilen yol bir dosya değil.")
    try:
        before = path.read_bytes() if path.exists() else b""
        before.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return _error("Yalnız metin dosyaları düzenlenebilir.")
    actual = hashlib.sha256(before).hexdigest() if path.exists() else ""
    if actual != expected:
        return {
            "ok": False,
            "kod": "STALE_FILE",
            "metin": "Dosya başka bir işlem tarafından değiştirildi. Yeniden yükleyip tekrar dene.",
        }
    after = content.encode("utf-8")
    if before == after:
        return _error("Dosyada değişiklik yok.")
    relative = _relative(root, path)
    diff, added, removed = _diff(relative, before, after)
    existed = path.exists()
    mode = path.stat().st_mode if existed else None
    try:
        _atomic_write(path, after, mode=mode)
    except OSError:
        return _error("Dosya yazılamadı.")
    journal.record(UndoEntry(relative, existed, before, after, diff, added, removed))
    return {
        "ok": True,
        "yol": relative,
        "sha256": hashlib.sha256(after).hexdigest(),
        "diff": diff,
        "added": added,
        "removed": removed,
    }


def _change_payload(path: str, diff: str, *, can_undo: bool) -> dict[str, Any]:
    lines = diff.splitlines()
    return {
        "yol": path,
        "diff": diff,
        "added": sum(1 for line in lines if line.startswith("+") and not line.startswith("+++")),
        "removed": sum(1 for line in lines if line.startswith("-") and not line.startswith("---")),
        "geri_alinabilir": can_undo,
    }


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_changes(root: Path) -> list[dict[str, Any]] | None:
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status is None or status.returncode != 0:
        return None
    records = [record for record in status.stdout.split(b"\0") if record]
    changes: list[dict[str, Any]] = []
    index = 0
    while index < len(records):
        record = records[index]
        if len(record) < 4:
            index += 1
            continue
        flags = record[:2].decode("ascii", errors="replace")
        path = record[3:].decode("utf-8", errors="replace")
        if flags[0] in {"R", "C"} and index + 1 < len(records):
            index += 1  # -z biçiminde yeniden adlandırmanın diğer yolu ayrı kayıttır.
        diff = ""
        if flags == "??":
            try:
                target = _resolve_inside(root, path)
                raw = target.read_bytes()
                if len(raw) > _DEFAULT_MAX_BYTES:
                    raw = raw[:_DEFAULT_MAX_BYTES]
                diff, _added, _removed = _diff(path, b"", raw)
            except (OSError, UnicodeDecodeError, WorkspacePathError):
                diff = f"Binary veya okunamayan yeni dosya: {path}"
        else:
            pieces: list[str] = []
            if flags[0] != " ":
                staged = _git(root, "diff", "--cached", "--no-ext-diff", "--unified=3", "--", path)
                if staged is not None and staged.returncode == 0:
                    pieces.append(staged.stdout.decode("utf-8", errors="replace"))
            if flags[1] != " ":
                unstaged = _git(root, "diff", "--no-ext-diff", "--unified=3", "--", path)
                if unstaged is not None and unstaged.returncode == 0:
                    pieces.append(unstaged.stdout.decode("utf-8", errors="replace"))
            diff = "\n".join(piece.rstrip() for piece in pieces if piece).strip()
        changes.append(_change_payload(path, diff, can_undo=True))
        index += 1
    return sorted(changes, key=lambda item: str(item["yol"]).casefold())


def list_changes(root: Path, journal: WorkspaceJournal) -> dict[str, Any]:
    latest = journal.latest()
    git_changes = _git_changes(root)
    if git_changes is not None:
        return {"ok": True, "degisiklikler": git_changes}
    return {
        "ok": True,
        "degisiklikler": [
            {
                "yol": entry.path,
                "diff": entry.diff,
                "added": entry.added,
                "removed": entry.removed,
                "geri_alinabilir": True,
            }
            for entry in latest
        ],
    }


def undo_entry(root: Path, data: dict[str, Any], journal: WorkspaceJournal) -> dict[str, Any]:
    try:
        path = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    relative = _relative(root, path)
    entry = journal.pop(relative)
    if entry is None:
        return _undo_git_entry(root, path, relative)
    try:
        if entry.existed:
            mode = path.stat().st_mode if path.exists() else None
            _atomic_write(path, entry.before, mode=mode)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        journal.record(entry)
        return _error("Dosya geri alınamadı.")
    return {
        "ok": True,
        "yol": relative,
        "sha256": hashlib.sha256(entry.before).hexdigest() if entry.existed else "",
        "metin": "Dosya önceki sürümüne döndürüldü.",
    }


def _undo_git_entry(root: Path, path: Path, relative: str) -> dict[str, Any]:
    """UI dışındaki agent değişikliğini Git taban çizgisine tek dosyada döndür."""
    if not (root / ".git").exists():
        return _error("Bu dosya için geri alınabilir bir değişiklik yok.")
    tracked = _git(root, "ls-files", "--error-unmatch", "--", relative)
    if tracked is not None and tracked.returncode == 0:
        restored = _git(root, "restore", "--source=HEAD", "--staged", "--worktree", "--", relative)
        if restored is None or restored.returncode != 0:
            return _error("Dosya Git sürümüne döndürülemedi.")
    else:
        status = _git(root, "status", "--porcelain=v1", "--", relative)
        if status is None or not status.stdout.startswith(b"?? ") or not path.is_file():
            return _error("Bu dosya için geri alınabilir bir değişiklik yok.")
        try:
            path.unlink()
        except OSError:
            return _error("Yeni dosya kaldırılamadı.")
    content = path.read_bytes() if path.exists() else b""
    return {
        "ok": True,
        "yol": relative,
        "sha256": hashlib.sha256(content).hexdigest() if content else "",
        "metin": "Dosya Git taban sürümüne döndürüldü.",
    }
