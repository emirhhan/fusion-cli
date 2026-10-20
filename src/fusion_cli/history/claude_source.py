"""Claude Code oturum geçmişi okuyucusu.

Claude her oturumu `~/.claude/projects/<slug>/<oturum>.jsonl` altında, satır başına
bir JSON kaydı olarak tutar. Slug, çalışma dizini yolundaki `/` karakterlerinin
`-` ile değiştirilmiş halidir.

İki tuzak vardır ve ikisi de gerçek veriden ölçüldü:

- `message.content` ya düz metin ya da parça listesidir; ikisi de karşılanmalı.
- Oturumların yalnızca bir kısmında `ai-title` kaydı bulunur (ölçüm: 47'de 13).
  Bu yüzden başlık çözümü basamaklıdır.
"""

from __future__ import annotations

import builtins
import json
from collections.abc import Generator
from pathlib import Path

from .models import SessionRef, Turn, fallback_title

#: Başlık olarak kullanılacak metnin en fazla uzunluğu.
TITLE_BUDGET = 60

#: Kullanıcı mesajı gibi görünen ama CLI'ın kendi ürettiği sarmalayıcılar. Bunlar
#: başlık olarak gösterilirse liste anlamsızlaşır.
_NOISE_PREFIXES = ("<local-command-caveat>", "<command-name>", "<command-message>")


def slug_for(root: Path) -> str:
    """Çalışma dizinini Claude'un proje dizini adına çevir."""
    return str(root).replace("/", "-")


def _text_of(message: object) -> str:
    """`content` alanını düz metne çevir. Parça listesi de düz metin de olabilir.

    `message` sözlük değilse (ör. `None`, düz metin, liste) boş dizge döner;
    çağıran taraf bunu `cast` ile sözlük varsayıp riske atmamalıdır.
    """
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _is_noise(text: str) -> bool:
    return text.startswith(_NOISE_PREFIXES)


class ClaudeSource:
    """Claude Code geçmişini okur. Hiçbir metodu istisna fırlatmaz."""

    name = "claude"

    def __init__(self, home: Path) -> None:
        self._home = home

    def _projects_root(self) -> Path:
        return self._home / ".claude" / "projects"

    def is_installed(self) -> bool:
        return self._projects_root().is_dir()

    def _session_paths(self) -> list[Path]:
        base = self._projects_root()
        if not base.is_dir():
            return []
        return sorted(base.glob("*/*.jsonl"))

    def _sorted_candidates(self, wanted_slug: str | None) -> list[Path]:
        """Aday dosyaları içerik OKUNMADAN sırala.

        Sıralama anahtarı yalnızca `stat().st_mtime` ve proje aidiyetidir; ikisi
        de dosya açılmadan bilinir. Bu, `list` çağıranın `limit` verdiği durumda
        gereksiz JSONL ayrıştırmasını baştan önlemeyi mümkün kılar. `stat()`
        başarısız olan dosya sessizce atlanır.
        """
        candidates: list[tuple[bool, float, Path]] = []
        for path in self._session_paths():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            is_other_project = wanted_slug is not None and path.parent.name != wanted_slug
            candidates.append((is_other_project, mtime, path))
        # `root` verilmişse o projeye ait oturumlar önce gelir; diğer projeler
        # kaybolmaz, yalnızca geriye itilir. Öncelik grubu içinde ise en yeni
        # oturum baştadır.
        candidates.sort(key=lambda c: (c[0], -c[1]))
        return [path for _, _, path in candidates]

    def list(self, root: Path | None = None, limit: int | None = None) -> tuple[SessionRef, ...]:
        wanted_slug = slug_for(root) if root is not None else None
        ordered_paths = self._sorted_candidates(wanted_slug)
        return self._refs_from_paths(ordered_paths, limit)

    def list_for_root(self, root: Path, limit: int | None = None) -> tuple[SessionRef, ...]:
        """Yalnızca Claude slug'ı `root` ile birebir eşleşen oturumları döndür."""
        project = self._projects_root() / slug_for(root)
        if not project.is_dir():
            return ()
        candidates: list[tuple[float, Path]] = []
        for path in project.glob("*.jsonl"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        return self._refs_from_paths([path for _, path in candidates], limit)

    def _refs_from_paths(
        self, ordered_paths: builtins.list[Path], limit: int | None
    ) -> tuple[SessionRef, ...]:
        if limit is not None:
            ordered_paths = ordered_paths[:limit]
        refs: builtins.list[SessionRef] = []
        for path in ordered_paths:
            ref = self._read_ref(path)
            if ref is not None:
                refs.append(ref)
        return tuple(refs)

    def _read_ref(self, path: Path) -> SessionRef | None:
        title = ""
        first_user = ""
        turn_count = 0
        for record in self._records(path):
            kind = record.get("type")
            if kind == "ai-title":
                title = str(record.get("aiTitle") or "").strip()
            elif kind in ("user", "assistant"):
                turn_count += 1
                if kind == "user" and not first_user:
                    text = _text_of(record.get("message"))
                    if text and not _is_noise(text):
                        first_user = text.splitlines()[0][:TITLE_BUDGET]
        try:
            stat_result = path.stat()
        except OSError:
            return None
        updated_at = stat_result.st_mtime
        size_bytes = stat_result.st_size
        return SessionRef(
            source=self.name,
            session_id=path.stem,
            title=title or first_user or fallback_title(updated_at, size_bytes),
            updated_at=updated_at,
            turn_count=turn_count,
            size_bytes=size_bytes,
        )

    def _records(self, path: Path) -> Generator[dict[str, object], None, None]:
        """Dosyayı satır satır oku; bozuk satırı atla. Bellekte tamamı tutulmaz."""
        try:
            handle = path.open(encoding="utf-8", errors="ignore")
        except OSError:
            return
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(record, dict):
                    yield record

    def _find(self, session_id: str) -> Path | None:
        base = self._projects_root()
        if not base.is_dir():
            return None
        return next(
            (path for path in sorted(base.glob("*/*.jsonl")) if path.stem == session_id),
            None,
        )

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        path = self._find(session_id)
        if path is None:
            return ()
        turns: list[Turn] = []
        seen = 0
        for record in self._records(path):
            if record.get("type") not in ("user", "assistant"):
                continue
            if record.get("isMeta") or record.get("isSidechain"):
                continue
            text = _text_of(record.get("message"))
            if not text:
                continue
            if seen < cursor:
                seen += 1
                continue
            turns.append(
                Turn(
                    role=str(record.get("type")),
                    text=text,
                    timestamp=_epoch(record.get("timestamp")),
                )
            )
            seen += 1
            if len(turns) >= limit:
                break
        return tuple(turns)


def _epoch(value: object) -> float:
    """ISO zaman damgasını unix saniyeye çevir. Çözülemezse 0 döner."""
    if not isinstance(value, str):
        return 0.0
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
