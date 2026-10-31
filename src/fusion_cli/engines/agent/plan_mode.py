"""Plan kipi dosyası: planın nereye yazıldığı ve ne zaman yazıldığı (P-025).

Claude Code plan kipinde planı `~/.claude/plans/` altında Markdown tutar ve tur
bitince "uygulansın mı?" kartı gösterir. Fusion'da plan kipindeki turun SON cevabı
plandır (bkz. `prompts/plan_mode.md`); tur bitince `record_plan` onu
`plans_dir()/<sohbet>.md` dosyasına yazar ve `PlanDrafted` yayınlar. Kabul kartı
yüzeylerde yaşar: REPL `cli/repl/plan_card.py`, masaüstü `SessionApplication.tsx`.

Ölçüldü (31 Ekim): plan kipinde tur bitince plan hiçbir yere yazılmıyordu; kullanıcı
planı ancak sohbet geçmişinden geri kaydırarak bulabiliyordu.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.paths import plans_dir
from ...core.events import PlanDrafted
from ...ui import messages

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from .loop import AgentDeps, AgentOutcome

#: Dosya adında kalabilen karakterler; gerisi alt çizgi olur (`..`/`/` kök dışına çıkaramaz).
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
#: Sohbet kimliği boşsa (tek atışlık `fusion agent`) kullanılan dosya adı.
_DEFAULT_STEM = "oturum"


def plan_path(conversation_id: str) -> Path:
    """Sohbetin plan dosyası. Kimlik dosya adına indirgenir, dizin daima `plans_dir()`."""
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or _DEFAULT_STEM
    return plans_dir() / f"{stem}.md"


def save_plan(conversation_id: str, markdown: str) -> Path:
    """Planı dosyaya yaz (üzerine yazar: aynı sohbetin planı tek dosyadır)."""
    path = plan_path(conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def read_plan(conversation_id: str) -> str | None:
    """Sohbetin kayıtlı planı; yoksa None."""
    path = plan_path(conversation_id)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def plan_title(markdown: str) -> str:
    """İlk Markdown başlığı; yoksa ilk dolu satır; o da yoksa genel ad."""
    first_line = ""
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip() or messages.PLAN_UNTITLED
        if not first_line:
            first_line = line
    return first_line or messages.PLAN_UNTITLED


def record_plan(outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool) -> Path | None:
    """Plan kipindeki başarılı turun cevabını plan dosyasına yaz ve olayını yayınla.

    Plan kipi dışında, başarısız ya da boş turda ve `runtime.plan_files` kapalıyken
    hiçbir şey yapılmaz. Yazma hatası turu düşürmez: plan sohbette zaten duruyor.
    """
    text = outcome.final_text.strip()
    if not plan_mode or not outcome.ok or not text or not deps.config.runtime.plan_files:
        return None
    try:
        path = save_plan(deps.conversation_id, outcome.final_text)
    except OSError:
        return None
    deps.publisher.publish(PlanDrafted(path=str(path), title=plan_title(text)))
    return path
