"""Masaüstü uygulaması için proje-kökü sınırlı salt-okunur çalışma alanı.

Bu katman UI'ın dosya sistemine doğrudan erişmesini engeller. Bütün yollar tek
bir sınır fonksiyonundan geçer; sembolik bağlar dahil gerçek hedef proje
kökünün dışına çıkamaz.
"""

from __future__ import annotations

import base64
import codecs
import hashlib
import os
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from ..core.changeset import Snapshot
from .workspace_journal import OWNER_AGENT, UndoEntry, WorkspaceJournal, text_diff

__all__ = [
    "UndoEntry",
    "WorkspaceJournal",
    "list_changes",
    "read_entry",
    "record_agent_changes",
    "undo_entry",
    "write_entry",
]

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 200
_DEFAULT_MAX_BYTES = 256 * 1024
_MAX_READ_BYTES = 2 * 1024 * 1024
_MAX_PREVIEW_BYTES = 8 * 1024 * 1024
#: Bu boyutun üstündeki dosyaların özeti hesaplanmaz (boş döner): yalnız örnek okunur.
_MAX_DIGEST_BYTES = 256 * 1024 * 1024
_DIGEST_CHUNK_BYTES = 1024 * 1024
#: Tek `proje.degisiklikler` yanıtında ayrıntılı diff üretilen en çok dosya. Fazlası listede
#: yer alır ama diff'siz; her dosya için git'i yeniden çalıştırmak olay döngüsünü tutardı.
MAX_DETAILED_CHANGES = 100
_OUTSIDE = "Proje klasörünün dışına çıkılamaz."


class WorkspacePathError(ValueError):
    """Kullanıcı yolu proje sınırını ihlal etti."""


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


def resolve_workspace_path(root: Path, raw: object) -> Path:
    """Diğer appserver servisleri için kanonik proje-kökü sınırı."""
    return _resolve_inside(root, raw)


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


#: Uzantı → MIME. Açık eşleme, `mimetypes` modülü YERİNE kullanılır.
#
# Ölçüldü (Windows CI, run 34591998944): `proje.oku` isteği paketlenmiş runtime'da
# 30 saniyede yanıt vermedi ve Windows kurucusu hiç üretilemedi. Zincir şuydu —
# `proje.listele` tür tahmini yapmıyor ve hızlı geçiyor; `proje.oku` ise `mimetypes`
# modülünü İLK kez kullanan istek ve o modülün tembel ilk kurulumu Windows'ta
# `read_windows_registry()` ile HKEY_CLASSES_ROOT'u tarıyor. Donmuş (PyInstaller)
# bir exe içinde bu tarama kullanıcının isteğini bloke ediyor.
#
# İkinci ve daha önemli gerekçe: tür tahmini kullanıcının KAYIT DEFTERİNE göre
# değişmemeli. Aynı dosya her makinede aynı türü vermelidir; `mimetypes` bunu
# garanti etmiyor çünkü Windows'ta sistem yapılandırmasını okur.
_MIME_BY_SUFFIX: dict[str, str] = {
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".css": "text/css",
    ".csv": "text/csv",
    ".gif": "image/gif",
    ".htm": "text/html",
    ".html": "text/html",
    ".ico": "image/vnd.microsoft.icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript",
    ".json": "application/json",
    ".m4a": "audio/mp4",
    ".md": "text/markdown",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ogg": "audio/ogg",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".toml": "application/toml",
    ".ts": "text/typescript",
    ".txt": "text/plain",
    ".wav": "audio/wav",
    ".webm": "video/webm",
    ".webp": "image/webp",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


def guess_mime(name: str) -> str | None:
    """Dosya adından MIME türünü tahmin et; bilinmiyorsa None.

    Kararı çağırana bırakır: okuma yolunda ikili dosya `octet-stream`, metin
    `text/plain` olur; önizleme yolunda bilinmeyen tür `octet-stream` sayılır.
    """
    suffix = PurePosixPath(name.lower()).suffix
    return _MIME_BY_SUFFIX.get(suffix)


def _mime(path: Path, *, binary: bool) -> str:
    guessed = guess_mime(path.name)
    if guessed:
        return guessed
    return "application/octet-stream" if binary else "text/plain"


def _sample_and_digest(path: Path, max_bytes: int) -> tuple[bytes, str, int]:
    """(örnek, sha256, boyut): dosyanın tamamı belleğe alınmadan, akışla.

    `max_bytes` yalnız dilimleme içindir; 2 GB'lık bir günlük `read_bytes` ile belleğe
    girerdi. `_MAX_DIGEST_BYTES` üstünde özet hesaplanmaz ("" döner).
    """
    size = path.stat().st_size
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        sample = handle.read(max_bytes)
        if size > _MAX_DIGEST_BYTES:
            return sample, "", size
        hasher.update(sample)
        total = len(sample)
        while chunk := handle.read(_DIGEST_CHUNK_BYTES):
            hasher.update(chunk)
            total += len(chunk)
    return sample, hasher.hexdigest(), total


def read_entry(
    root: Path, data: dict[str, Any], journal: WorkspaceJournal | None = None
) -> dict[str, Any]:
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
        sample, digest, size = _sample_and_digest(path, max_bytes)
    except OSError:
        return _error("Dosya okunamadı.")
    truncated = size > max_bytes
    binary = b"\x00" in sample
    text: str | None = None
    if not binary:
        try:
            # Kesilmiş örnekte sondaki yarım çok baytlı karakter hata sayılmaz (final=False).
            text = codecs.getincrementaldecoder("utf-8")().decode(sample, final=not truncated)
        except UnicodeDecodeError:
            binary = True
    if journal is not None and not truncated and not binary:
        journal.note_full_read(_relative(root, path), digest)
    return {
        "ok": True,
        "yol": _relative(root, path),
        "tur": "binary" if binary else "metin",
        "mime": _mime(path, binary=binary),
        "boyut": size,
        "sha256": digest,
        "icerik": None if binary else text,
        "kesildi": truncated,
    }


def preview_entry(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Desteklenen bir asset'i kök sınırı ve sabit boyut tavanıyla döndürür."""
    try:
        path = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    if not path.exists() or not path.is_file():
        return _error("Dosya bulunamadı.")
    mime = guess_mime(path.name) or "application/octet-stream"
    if mime.startswith("image/"):
        kind = "image"
    elif mime.startswith("audio/"):
        kind = "audio"
    elif mime.startswith("video/"):
        kind = "video"
    elif mime == "application/pdf":
        kind = "pdf"
    elif mime in {"text/html", "application/xhtml+xml"}:
        kind = "html"
    elif mime.startswith("text/"):
        kind = "text"
    else:
        return {
            "ok": False,
            "kod": "UNSUPPORTED_PREVIEW",
            "metin": "Bu dosya türü uygulama içinde önizlenemiyor.",
        }
    try:
        size = path.stat().st_size
        if size > _MAX_PREVIEW_BYTES:
            return {
                "ok": False,
                "kod": "PREVIEW_TOO_LARGE",
                "metin": "Önizleme için dosya 8 MB sınırını aşıyor.",
            }
        raw = path.read_bytes()
    except OSError:
        return _error("Dosya okunamadı.")
    return {
        "ok": True,
        "yol": _relative(root, path),
        "tur": kind,
        "mime": mime,
        "boyut": len(raw),
        "base64": base64.b64encode(raw).decode("ascii"),
    }


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
    relative = _relative(root, path)
    if path.exists() and not journal.has_full_read(relative, expected):
        # Karma dosyanın tamamına aittir ama istemci yalnız kesilmiş önizlemeyi
        # görmüş olabilir: o içerikle yazmak dosyanın geri kalanını siler.
        return {
            "ok": False,
            "kod": "PARTIAL_READ",
            "metin": "Dosyanın tamamı okunmadan kaydedilemez. Dosyayı yeniden açıp tekrar dene.",
        }
    after = content.encode("utf-8")
    if before == after:
        return _error("Dosyada değişiklik yok.")
    diff, added, removed = text_diff(relative, before, after)
    existed = path.exists()
    mode = path.stat().st_mode if existed else None
    try:
        _atomic_write(path, after, mode=mode)
    except OSError:
        return _error("Dosya yazılamadı.")
    journal.record(UndoEntry(relative, existed, before, after, diff, added, removed))
    written_sha = hashlib.sha256(after).hexdigest()
    journal.note_full_read(relative, written_sha)
    return {
        "ok": True,
        "yol": relative,
        "sha256": written_sha,
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


def _git_changes(root: Path, journal: WorkspaceJournal) -> list[dict[str, Any]] | None:
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status is None or status.returncode != 0:
        return None
    records = [record for record in status.stdout.split(b"\0") if record]
    changes: list[dict[str, Any]] = []
    detailed = 0
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
        if detailed >= MAX_DETAILED_CHANGES:
            pass  # sınır aşıldı: dosya listede kalır, diff'i için git/dosya okunmaz
        elif flags == "??":
            detailed += 1
            try:
                target = _resolve_inside(root, path)
                with target.open("rb") as handle:
                    raw = handle.read(_DEFAULT_MAX_BYTES)
                diff, _added, _removed = text_diff(path, b"", raw)
            except (OSError, UnicodeDecodeError, WorkspacePathError):
                diff = f"Binary veya okunamayan yeni dosya: {path}"
        else:
            detailed += 1
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
        changes.append(_change_payload(path, diff, can_undo=journal.owns(path)))
        index += 1
    return sorted(changes, key=lambda item: str(item["yol"]).casefold())


def list_changes(root: Path, journal: WorkspaceJournal) -> dict[str, Any]:
    latest = journal.latest()
    git_changes = _git_changes(root, journal)
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


_NOT_OWNED = {
    "ok": False,
    "kod": "NOT_OWNED",
    "metin": ("Bu dosya için Fusion'ın kaydettiği bir önceki sürüm yok; dosyaya dokunulmadı."),
}
_CONFLICT = {
    "ok": False,
    "kod": "CONFLICT",
    "metin": (
        "Dosya Fusion'ın değişikliğinden sonra yeniden değişti; geri alma sonraki "
        "değişikliği sileceği için yapılmadı."
    ),
}


def undo_entry(root: Path, data: dict[str, Any], journal: WorkspaceJournal) -> dict[str, Any]:
    """Fusion'ın son değişikliğini, dosya o değişiklikten sonra değişmediyse geri al."""
    try:
        path = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    relative = _relative(root, path)
    entry = journal.peek(relative)
    if entry is None:
        return dict(_NOT_OWNED)
    try:
        if _current_bytes(path) != (entry.after if entry.exists_after else None):
            return dict(_CONFLICT)
        if entry.existed:
            mode = path.stat().st_mode if path.exists() else None
            _atomic_write(path, entry.before, mode=mode)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return _error("Dosya geri alınamadı.")
    journal.pop(relative)
    return {
        "ok": True,
        "yol": relative,
        "sha256": hashlib.sha256(entry.before).hexdigest() if entry.existed else "",
        "metin": "Dosya önceki sürümüne döndürüldü.",
    }


def record_agent_changes(
    root: Path, journal: WorkspaceJournal, snapshots: Iterable[Snapshot]
) -> None:
    """Ajan turunun ilk-hâl anlık görüntülerini geri alınabilir kayıtlara çevir.

    Kök dışındaki, okunamayan veya değişmemiş yollar atlanır; kaydı olmayan dosya
    geri alınamaz, yanlış içerikle geri yazılmaz.
    """
    base = root.resolve()
    for snapshot in snapshots:
        try:
            inside = snapshot.path.resolve().relative_to(base).as_posix()
            path = _resolve_inside(root, inside)
            current = _current_bytes(path)
        except (ValueError, WorkspacePathError, OSError):
            continue
        relative = _relative(root, path)
        if current == snapshot.content:
            continue
        before = snapshot.content or b""
        after = current or b""
        try:
            diff, added, removed = text_diff(relative, before, after)
        except UnicodeDecodeError:
            diff, added, removed = f"Binary dosya değişti: {relative}", 0, 0
        journal.record(
            UndoEntry(
                relative,
                snapshot.existed,
                before,
                after,
                diff,
                added,
                removed,
                exists_after=current is not None,
                owner=OWNER_AGENT,
            )
        )


def _current_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
