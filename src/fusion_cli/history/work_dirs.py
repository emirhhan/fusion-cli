"""Codex oturumunun gerçekte çalıştığı proje klasörlerini bulur.

Codex mesajlarda klasör yolu neredeyse hiç yazmaz; yollar araç çağrılarında durur
(`rollout-*.jsonl`). Devralınan sohbette bunlar kaybolunca Fusion yanlış proje
kökünde aramaya devam ediyordu (20 Ekim: Summertime Saga çevirisi VFS-BOT içinde
arandı). Burada yalnızca yol METNİ taranır; hiçbir dosya içeriği okunmaz.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

#: Ev dizini altında proje barındıran genel üst klasörler: asıl proje bir alt düzeydedir.
_GENEL_UST = frozenset({"Desktop", "Documents", "Downloads", "Projects", "Developer", "Code"})
#: Ev dizininde asla proje sayılmayan klasörler.
_DISLANAN = frozenset({"Library", "Applications", "Movies", "Music", "Pictures", "Public"})
_YOL_SONU = r"""[^\s"'`\\),;:<>|*?]+"""


def codex_work_dirs(home: Path, session_id: str, limit: int = 4) -> tuple[Path, ...]:
    """Oturumda en sık geçen, var olan proje klasörleri (sıklığa göre)."""
    rollout = _find_rollout(home, session_id)
    if rollout is None:
        return ()
    desen = re.compile(re.escape(str(home)) + "/" + _YOL_SONU)
    sayac: Counter[Path] = Counter()
    try:
        with rollout.open(encoding="utf-8", errors="ignore") as satirlar:
            for satir in satirlar:
                for eslesme in desen.findall(satir):
                    proje = _project_dir(home, Path(eslesme))
                    if proje is not None:
                        sayac[proje] += 1
    except OSError:
        return ()
    return tuple(yol for yol, _ in sayac.most_common(limit))


def _find_rollout(home: Path, session_id: str) -> Path | None:
    if not session_id or "/" in session_id or "\\" in session_id:
        return None
    sessions = home / ".codex" / "sessions"
    try:
        return next(sessions.glob(f"**/rollout-*{session_id}.jsonl"), None)
    except OSError:
        return None


def _project_dir(home: Path, path: Path) -> Path | None:
    try:
        parts = path.relative_to(home).parts
    except ValueError:
        return None
    if not parts or parts[0].startswith(".") or parts[0] in _DISLANAN:
        return None
    derinlik = 2 if parts[0] in _GENEL_UST else 1
    if len(parts) < derinlik:
        return None
    aday = home.joinpath(*parts[:derinlik])
    return aday if aday.is_dir() and aday != home else None
