"""Oturum hedefi (`/goal <koşul>`, P-058): turlar arası devam koşulu ve karar makinesi.

Claude Code `/goal` modeli: kullanıcı bir BİTİŞ KOŞULU verir; her tur bitince ucuz bir
değerlendirici koşulun karşılanıp karşılanmadığına karar verir. "Henüz değil" ise tur
kendiliğinden sürer; "Tamam" ya da "İmkânsız" ise hedef kapanır. Uzun koşu belirli
aralıklarla kullanıcıya danışmak için durur (check-in; 30 dk, sonra katlanarak) ve
otomatik tur sayısı bir tavanla sınırlıdır (kota ve kaçak döngü koruması).

Yalnız stdlib; zaman dışarıdan verilir. Değerlendirme (model çağrısı) `engines` katmanında,
yüzeylere bağlama `cli` katmanındadır. Ölçüldü (31 Ekim): `/goal` yalnız tek turluk bir
"pes etme" kipiydi; kalıcı koşul, tur sonu değerlendirici ve İmkânsız çıkışı yoktu.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from enum import Enum

from .errors import FusionError

#: Koşul metninin tavanı (Claude Code ile aynı: 4.000 karakter).
MAX_CONDITION_CHARS = 4000
#: Değerlendirici gerekçesinin saklanan/gösterilen tavanı.
MAX_REASON_CHARS = 400


class GoalError(FusionError):
    """Hedef girdisi geçersiz; mesaj kullanıcıya gösterilir."""


class GoalVerdict(Enum):
    """Değerlendiricinin kararı; değer JSON'daki `karar` alanıdır."""

    NOT_MET = "henuz_degil"
    MET = "tamam"
    IMPOSSIBLE = "imkansiz"
    #: Değerlendirici yanıt vermedi ya da yanıt okunamadı: otomatik devam YAPILMAZ.
    UNKNOWN = "belirsiz"


class PauseReason(Enum):
    """Hedef neden duraklatıldı? Boş değer = etkin."""

    NONE = ""
    CHECKIN = "danisma"
    TURN_LIMIT = "tur_siniri"
    UNKNOWN_VERDICT = "belirsiz_karar"


class GoalAction(Enum):
    """Tur sonu kararının yüzeye söylediği iş."""

    CONTINUE = "devam"
    MET = "tamam"
    IMPOSSIBLE = "imkansiz"
    PAUSED = "duraklatildi"


@dataclass(frozen=True, slots=True)
class SessionGoal:
    """Etkin (ya da duraklatılmış) oturum hedefi."""

    condition: str
    started_at: float
    next_checkin_at: float
    #: Sıradaki danışmaya kadar süre (sn); 0 = danışma kapalı. Her devamda ikiye katlanır.
    checkin_interval_s: float
    #: Değerlendirilen tur sayısı (kullanıcı turları dahil).
    evaluations: int = 0
    #: Kullanıcı yazmadan başlatılan devam turu sayısı (tavanla sınırlı).
    auto_turns: int = 0
    paused: PauseReason = PauseReason.NONE
    last_verdict: GoalVerdict | None = None
    last_reason: str = ""

    @property
    def is_active(self) -> bool:
        return self.paused is PauseReason.NONE

    def to_dict(self) -> dict[str, object]:
        return {
            "kosul": self.condition,
            "baslangic": self.started_at,
            "sonraki_danisma": self.next_checkin_at,
            "danisma_araligi_s": self.checkin_interval_s,
            "degerlendirme": self.evaluations,
            "otomatik_tur": self.auto_turns,
            "duraklama": self.paused.value,
            "son_karar": self.last_verdict.value if self.last_verdict else None,
            "son_gerekce": self.last_reason,
        }

    @classmethod
    def from_dict(cls, data: object) -> SessionGoal | None:
        """Bozuk kayıt hedefi düşürür (None), oturumu düşürmez."""
        if not isinstance(data, dict):
            return None
        try:
            verdict = data.get("son_karar")
            return cls(
                condition=str(data["kosul"]),
                started_at=float(data["baslangic"]),
                next_checkin_at=float(data["sonraki_danisma"]),
                checkin_interval_s=float(data.get("danisma_araligi_s", 0)),
                evaluations=int(data.get("degerlendirme", 0)),
                auto_turns=int(data.get("otomatik_tur", 0)),
                paused=PauseReason(data.get("duraklama", "")),
                last_verdict=GoalVerdict(verdict) if verdict else None,
                last_reason=str(data.get("son_gerekce", "")),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class GoalStep:
    """Bir tur sonu kararının sonucu: yeni hedef durumu (kapandıysa None) ve iş."""

    goal: SessionGoal | None
    action: GoalAction
    verdict: GoalVerdict
    reason: str


def new_goal(condition: str, *, now: float, checkin_minutes: float) -> SessionGoal:
    """Koşuldan yeni hedef; boş ya da tavanı aşan koşul `GoalError`."""
    text = (condition or "").strip()
    if not text:
        raise GoalError("Hedef koşulu boş olamaz. Örnek: /goal tüm testler geçiyor")
    if len(text) > MAX_CONDITION_CHARS:
        raise GoalError(f"Hedef koşulu en çok {MAX_CONDITION_CHARS} karakter olabilir.")
    interval = max(0.0, checkin_minutes) * 60
    return SessionGoal(
        condition=text,
        started_at=now,
        next_checkin_at=now + interval if interval else 0.0,
        checkin_interval_s=interval,
    )


def decide(
    goal: SessionGoal, verdict: GoalVerdict, reason: str, *, now: float, max_auto_turns: int
) -> GoalStep:
    """Değerlendirici kararını uygula. Karar makinesi saf ve sırasızdır."""
    clipped = (reason or "").strip()[:MAX_REASON_CHARS]
    judged = replace(
        goal, evaluations=goal.evaluations + 1, last_verdict=verdict, last_reason=clipped
    )
    if verdict is GoalVerdict.MET:
        return GoalStep(None, GoalAction.MET, verdict, clipped)
    if verdict is GoalVerdict.IMPOSSIBLE:
        return GoalStep(None, GoalAction.IMPOSSIBLE, verdict, clipped)
    if verdict is GoalVerdict.UNKNOWN:
        paused = replace(judged, paused=PauseReason.UNKNOWN_VERDICT)
        return GoalStep(paused, GoalAction.PAUSED, verdict, clipped)
    if judged.auto_turns >= max(1, max_auto_turns):
        paused = replace(judged, paused=PauseReason.TURN_LIMIT)
        return GoalStep(paused, GoalAction.PAUSED, verdict, clipped)
    if judged.checkin_interval_s and now >= judged.next_checkin_at:
        paused = replace(judged, paused=PauseReason.CHECKIN)
        return GoalStep(paused, GoalAction.PAUSED, verdict, clipped)
    running = replace(judged, auto_turns=judged.auto_turns + 1)
    return GoalStep(running, GoalAction.CONTINUE, verdict, clipped)


def resume(goal: SessionGoal, *, now: float) -> SessionGoal:
    """`/goal devam`: duraklamayı kaldır. Danışma aralığı katlanır, tur sayacı sıfırlanır."""
    interval = goal.checkin_interval_s
    if goal.paused is PauseReason.CHECKIN and interval:
        interval *= 2
    return replace(
        goal,
        paused=PauseReason.NONE,
        auto_turns=0,
        checkin_interval_s=interval,
        next_checkin_at=now + interval if interval else 0.0,
    )


def parse_verdict(text: str) -> GoalVerdict:
    """Değerlendirici `karar` değerini (Türkçe/İngilizce eş anlamlılarla) çöz."""
    # Aksan/noktalı İ düşürülür: "İmkânsız" → "imkansiz", "henüz değil" → "henuz_degil".
    folded = unicodedata.normalize("NFKD", (text or "").strip().casefold().replace("ı", "i"))
    key = "".join(char for char in folded if not unicodedata.combining(char))
    key = key.replace("-", "_").replace(" ", "_")
    return _VERDICT_WORDS.get(key, GoalVerdict.UNKNOWN)


_VERDICT_WORDS = {
    "henuz_degil": GoalVerdict.NOT_MET,
    "not_met": GoalVerdict.NOT_MET,
    "not_yet_met": GoalVerdict.NOT_MET,
    "tamam": GoalVerdict.MET,
    "met": GoalVerdict.MET,
    "imkansiz": GoalVerdict.IMPOSSIBLE,
    "impossible": GoalVerdict.IMPOSSIBLE,
}
