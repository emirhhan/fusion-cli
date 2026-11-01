"""Plan kipi dosyası: planın nereye yazıldığı ve ne zaman yazıldığı (P-025).

Claude Code plan kipinde planı `~/.claude/plans/` altında Markdown tutar ve tur
bitince "uygulansın mı?" kartı gösterir. Fusion'da plan `exit_plan_mode`
aracıyla sunulur (bkz. `prompts/plan_mode.md`); tur bitince `record_plan` onu
`plans_dir()/<sohbet>.md` dosyasına yazar ve `PlanDrafted` yayınlar. Kabul kartı
yüzeylerde yaşar: REPL `cli/repl/plan_card.py`, masaüstü `SessionApplication.tsx`.

Ölçüldü (31 Ekim): plan kipinde tur bitince plan hiçbir yere yazılmıyordu; kullanıcı
planı ancak sohbet geçmişinden geri kaydırarak bulabiliyordu.

Claude Code'daki gibi plan `exit_plan_mode` aracıyla açıkça sunulur (#317); araç
çağrılmayan tur (soru, sohbet) plan dosyasına dokunmaz ve kart açılmaz. Yeni plan
eskisinin üzerine yazılırken eskisi `<sohbet>.onceki.md` olarak saklanır.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.paths import plans_dir
from ...core.events import PlanDrafted
from ...ui import messages
from .approval import ApprovalMode, ApprovalPolicy, PlanApproval

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from .loop import AgentDeps, AgentOutcome

#: Dosya adında kalabilen karakterler; gerisi alt çizgi olur (`..`/`/` kök dışına çıkaramaz).
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
#: Sohbet kimliği boşsa (tek atışlık `fusion agent`) kullanılan dosya adı.
_DEFAULT_STEM = "oturum"
#: Üzerine yazılan önceki planın saklandığı dosya eki.
_PREVIOUS_SUFFIX = ".onceki.md"


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
    """`exit_plan_mode` ile onaya sunulan planı plan dosyasına yaz ve olayını yayınla.

    Claude Code'daki gibi plan YALNIZ araçla sunulur (#317): araç çağrılmadıysa (soru,
    sohbet, yarım keşif) dosyaya dokunulmaz ve kart açılmaz. `runtime.plan_files`
    kapalıyken ya da başarısız turda da yazılmaz. Yazma hatası turu düşürmez.
    """
    switch = getattr(deps.tool_context, "plan_mode_switch", None)
    if switch is None:
        return None
    submitted = switch.take_plan()
    if submitted is None or not submitted.strip():
        return None
    if not (plan_mode or switch.entered) or not outcome.ok or not deps.config.runtime.plan_files:
        return None
    try:
        path = save_plan(deps.conversation_id, submitted)
    except OSError:
        return None
    deps.publisher.publish(PlanDrafted(path=str(path), title=plan_title(submitted)))
    return path


def entered_plan_policy(deps: AgentDeps) -> ApprovalPolicy | None:
    """Tur içinde `enter_plan_mode` çağrıldıysa kalan çağrılar plan kipinin kurallarıyla (#324)."""
    switch = getattr(deps.tool_context, "plan_mode_switch", None)
    if switch is None or not switch.entered:
        return None
    builder = deps.policy_for_mode
    if builder is not None:
        return builder(ApprovalMode.PLAN)
    return PlanApproval()
