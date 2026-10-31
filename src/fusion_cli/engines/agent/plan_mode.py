"""Plan kipi dosyası: planın nereye yazıldığı ve ne zaman yazıldığı (P-025).

Claude Code plan kipinde planı `~/.claude/plans/` altında Markdown tutar ve tur
bitince "uygulansın mı?" kartı gösterir. Fusion'da plan kipindeki turun SON cevabı
plandır (bkz. `prompts/plan_mode.md`); tur bitince `record_plan` onu
`plans_dir()/<sohbet>.md` dosyasına yazar ve `PlanDrafted` yayınlar. Kabul kartı
yüzeylerde yaşar: REPL `cli/repl/plan_card.py`, masaüstü `SessionApplication.tsx`.

Ölçüldü (31 Ekim): plan kipinde tur bitince plan hiçbir yere yazılmıyordu; kullanıcı
planı ancak sohbet geçmişinden geri kaydırarak bulabiliyordu.

Claude Code'un açık `ExitPlanMode` adımı burada yok; bu yüzden plan kipindeki HER
cevap plan sayılmaz: soru ("Hangi veritabanı?") ve kısa sohbet cevapları
`looks_like_plan` ile ayrılır, önceki plan dosyasına dokunulmaz ve kart açılmaz.
Yeni plan eskisinin üzerine yazılırken eskisi `<sohbet>.onceki.md` olarak saklanır.
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
#: Üzerine yazılan önceki planın saklandığı dosya eki.
_PREVIOUS_SUFFIX = ".onceki.md"
#: Markdown liste ögesi: `- a`, `* a`, `1. a`, `1) a`.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
#: Bir planı "plan" saymak için gereken en az liste ögesi (başlık yoksa).
_MIN_LIST_ITEMS = 2


def plan_path(conversation_id: str) -> Path:
    """Sohbetin plan dosyası. Kimlik dosya adına indirgenir, dizin daima `plans_dir()`."""
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or _DEFAULT_STEM
    return plans_dir() / f"{stem}.md"


def previous_plan_path(conversation_id: str) -> Path:
    """Üzerine yazılan önceki planın yedeği (`<sohbet>.onceki.md`)."""
    path = plan_path(conversation_id)
    return path.with_name(path.stem + _PREVIOUS_SUFFIX)


def save_plan(conversation_id: str, markdown: str) -> Path:
    """Planı dosyaya yaz; aynı sohbetin planı tek dosyadır, eskisi `.onceki.md`ye alınır."""
    path = plan_path(conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = path.read_text(encoding="utf-8")
    except OSError:
        previous = None
    if previous is not None and previous != markdown:
        previous_plan_path(conversation_id).write_text(previous, encoding="utf-8")
    path.write_text(markdown, encoding="utf-8")
    return path


def looks_like_plan(markdown: str) -> bool:
    """Cevap plan mı, yoksa soru/sohbet mi?

    Plan: Markdown başlığı var (istem başlıkla başlamasını ister) YA DA en az iki liste
    ögesi var ve hiçbir satır soruyla bitmiyor. Soruyla biten ya da düz tek paragraf
    cevaplar plan değildir; önceki plan korunur, kart açılmaz.
    """
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    if not lines:
        return False
    if any(line.startswith("#") for line in lines):
        return True
    if any(line.endswith("?") for line in lines):
        return False
    return sum(1 for line in lines if _LIST_ITEM.match(line)) >= _MIN_LIST_ITEMS


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
    hiçbir şey yapılmaz; plana benzemeyen cevap (soru, kısa sohbet) da yazılmaz
    (`looks_like_plan`). Yazma hatası turu düşürmez: plan sohbette zaten duruyor.
    """
    text = outcome.final_text.strip()
    if not plan_mode or not outcome.ok or not text or not deps.config.runtime.plan_files:
        return None
    if not looks_like_plan(text):
        return None
    try:
        path = save_plan(deps.conversation_id, outcome.final_text)
    except OSError:
        return None
    deps.publisher.publish(PlanDrafted(path=str(path), title=plan_title(text)))
    return path
