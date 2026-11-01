"""Plan kipi araçlarının (`enter_plan_mode` / `exit_plan_mode`) tura bıraktığı istek.

Claude Code'da plan kipine `EnterPlanMode` aracıyla girilir, plan `ExitPlanMode` aracıyla
onaya sunulur (tools-reference). `ToolContext` donmuştur; araçlar isteği bu taşıyıcıya
yazar. Motor plan dosyasını yalnız `exit_plan_mode` çağrısından yazar (#317); yüzeyler
(REPL/TUI/masaüstü) tur bitince `enter_plan_mode` isteğini kipe uygular (#324).
"""

from __future__ import annotations


class PlanModeSwitch:
    """Tur boyunca yaşayan plan kipi durumu ve araç istekleri."""

    def __init__(self) -> None:
        #: Bu tur plan kipinde mi başladı (motor turu kurarken yazar)?
        self.active = False
        #: `enter_plan_mode` çağrıldı: turun geri kalanı plan kipinin kurallarıyla yürür.
        self.entered = False
        #: `exit_plan_mode` ile onaya sunulan plan (Markdown); sunulmadıysa None.
        self.submitted_plan: str | None = None

    @property
    def in_plan_mode(self) -> bool:
        return (self.active or self.entered) and self.submitted_plan is None

    def begin_turn(self, *, plan_mode: bool) -> None:
        """Kök tur başında önceki turun isteklerini temizle."""
        self.active = plan_mode
        self.entered = False
        self.submitted_plan = None

    def enter(self) -> None:
        self.entered = True

    def submit(self, plan: str) -> None:
        self.submitted_plan = plan

    def take_plan(self) -> str | None:
        """Sunulan planı bir kez al ve temizle."""
        plan, self.submitted_plan = self.submitted_plan, None
        return plan

    def take_enter(self) -> bool:
        """`enter_plan_mode` isteğini bir kez al ve temizle (yüzey kipi PLAN yapar)."""
        entered, self.entered = self.entered, False
        return entered
