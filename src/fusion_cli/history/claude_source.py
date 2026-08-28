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

import json
from collections.abc import Generator
from pathlib import Path

from .models import SessionRef, Turn

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

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        wanted_slug = slug_for(root) if root is not None else None
        entries: list[tuple[bool, float, SessionRef]] = []
        for path in self._session_paths():
            ref = self._read_ref(path)
            if ref is None:
                continue
            is_other_project = wanted_slug is not None and path.parent.name != wanted_slug
            entries.append((is_other_project, ref.updated_at, ref))
        # `root` verilmişse o projeye ait oturumlar önce gelir; diğer projeler
        # kaybolmaz, yalnızca geriye itilir. Öncelik grubu içinde ise en yeni
        # oturum baştadır (mevcut updated_at sıralaması korunur).
        entries.sort(key=lambda e: (e[0], -e[1]))
        return tuple(ref for _, _, ref in entries)

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
            updated_at = path.stat().st_mtime
        except OSError:
            return None
        return SessionRef(
            source=self.name,
            session_id=path.stem,
            title=title or first_user or path.stem,
            updated_at=updated_at,
            turn_count=turn_count,
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
        return next(iter(sorted(base.glob(f"*/{session_id}.jsonl"))), None)

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
