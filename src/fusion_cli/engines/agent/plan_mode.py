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
Claude'daki gibi eskisinin üzerine yazılır (#354). Eski Fusion davranışı (1 Kasım öncesi):
eski plan `<sohbet>.onceki.md` olarak saklanıyordu ve `runtime.plan_files: false` dosyayı
kapatıyordu; Claude'da ikisi de yok — ayar kullanımdan kalktı, okunur ve bir kez uyarılır.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.plans_location import legacy_directory, plans_directory
from ...core.events import PlanDrafted
from ...ui import messages
from .approval import ApprovalMode, ApprovalPolicy
from .plan_approval import PlanApproval

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi
    from .loop import AgentDeps, AgentOutcome

#: Dosya adında kalabilen karakterler; gerisi alt çizgi olur (`..`/`/` kök dışına çıkaramaz).
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
#: Sohbet kimliği boşsa (tek atışlık `fusion agent`) kullanılan dosya adı.
_DEFAULT_STEM = "oturum"
_LOG = logging.getLogger(__name__)
_PLAN_FILES_WARNED = False


def _stem(conversation_id: str) -> str:
    return _UNSAFE.sub("_", conversation_id).strip("._") or _DEFAULT_STEM


def plan_path(conversation_id: str, root: Path | None = None) -> Path:
    """Sohbetin plan dosyası: `plansDirectory` (varsayılan `~/.claude/plans`) altında (#354)."""
    return plans_directory(root) / f"{_stem(conversation_id)}.md"


def save_plan(conversation_id: str, markdown: str, root: Path | None = None) -> Path:
    """Planı dosyaya yaz; aynı sohbetin planı tek dosyadır ve üzerine yazılır (Claude)."""
    path = plan_path(conversation_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def _warn_plan_files_once(deps: AgentDeps) -> None:
    """`runtime.plan_files: false` Claude'da yok (#354): yok sayılır, süreçte bir kez uyarılır."""
    global _PLAN_FILES_WARNED
    if deps.config.runtime.plan_files or _PLAN_FILES_WARNED:
        return
    _PLAN_FILES_WARNED = True
    _LOG.warning(
        "runtime.plan_files kullanımdan kalktı ve yok sayılıyor: Claude Code planı her zaman "
        "plansDirectory altına yazar."
    )


def read_plan(conversation_id: str, root: Path | None = None) -> str | None:
    """Sohbetin kayıtlı planı; yoksa eski Fusion dizinine bakılır, orada da yoksa None."""
    for path in (
        plan_path(conversation_id, root),
        legacy_directory() / f"{_stem(conversation_id)}.md",
    ):
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
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
    sohbet, yarım keşif) dosyaya dokunulmaz ve kart açılmaz. Başarısız turda da yazılmaz.
    Yazma hatası turu düşürmez.
    """
    switch = getattr(deps.tool_context, "plan_mode_switch", None)
    if switch is None:
        return None
    submitted = switch.take_plan()
    if submitted is None or not submitted.strip():
        return None
    if not (plan_mode or switch.entered) or not outcome.ok:
        return None
    _warn_plan_files_once(deps)
    try:
        path = save_plan(deps.conversation_id, submitted, deps.tool_context.root)
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
