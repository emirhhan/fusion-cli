"""Becerinin `model` ve `effort` alanlarını O TURA uygulama (P-020).

Claude Code'da `model: claude-opus-…` ya da `effort: high` yazan beceri çağrıldığında o
tur o modelle/eforla koşar, sonraki tur oturumun seçimine döner. Fusion karşılığı: `/beceri`
işleyicisi seçimi bekleyen eklere koyar; tur yürütücüsü yalnız o turun yapılandırmasını
`TurnModelChoice.apply` ile değiştirir, oturumun `config`'i değişmez.

Model kimliği `<sağlayıcı>/<model>` olmalıdır (Fusion'ın tüm model alanları gibi);
`inherit` ve Claude'un kısa adları (`sonnet`, `opus`…) oturum modelini kullanır — alt ajan
tanımlarıyla aynı kural (`team_settings.INHERIT_MODELS`). Becerinin modeli birincil olur,
oturum modeli ve yedekleri zincirde kalır: beceri modeli kotaya takılırsa tur düşmez.
Görev türü haritası (`task_model_map`) o tur için devre dışıdır; yoksa harita becerinin
seçimini sessizce ezerdi.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ...config.models import Config
from ...core.reasoning import ReasoningEffort
from .team_settings import INHERIT_MODELS


@dataclass(frozen=True, slots=True)
class TurnModelChoice:
    """Tek turluk model/efor seçimi; boş = oturumun seçimi."""

    model: str = ""
    effort: ReasoningEffort | None = None

    @property
    def is_empty(self) -> bool:
        return not self.model and self.effort is None

    def apply(self, config: Config) -> Config:
        """Bu turun yapılandırması; seçim yoksa aynı nesne döner."""
        if self.is_empty:
            return config
        updated = config
        if self.model and self.model != config.agent.model:
            agent = dataclasses.replace(
                config.agent.with_identity(self.model),
                fallback=tuple(item for item in config.agent.models if item != self.model),
            )
            updated = dataclasses.replace(updated, agent=agent, task_model_map={})
        if self.effort is not None:
            updated = dataclasses.replace(
                updated,
                runtime=dataclasses.replace(updated.runtime, reasoning_effort=self.effort),
            )
        return updated


@dataclass(frozen=True, slots=True)
class TurnModelResolution:
    """Frontmatter değerlerinin çözümü ve kullanıcıya gösterilecek notlar."""

    choice: TurnModelChoice
    notes: tuple[str, ...] = ()


#: Güvenilmeyen projedeki beceri modeli değiştiremez (`fusion trust` ile açılır).
UNTRUSTED_MODEL_NOTE = (
    "model '{model}' uygulanmadı: proje becerisi güvenilmeyen projede modeli değiştiremez "
    "(`fusion trust` ile güven); oturum modeli kullanılacak"
)


def resolve_turn_model(model: str, effort: str, *, allow_model: bool = True) -> TurnModelResolution:
    """`model`/`effort` alanlarını seçime çevir; tanınmayan değer not düşer, uygulanmaz.

    `allow_model=False`: becerinin kaynağı depo içeriği ve proje güvenilmiyor. Ölçüldü
    (31 Ekim, bağımsız inceleme): güvenilmeyen bir deponun `/ad` becerisi `model:` ile turu
    (konuşma ve depo içeriğiyle) o proje için seçilmemiş bir sağlayıcıya yönlendirebiliyordu.
    Efor değişikliği veri yönlendirmediği için uygulanır.
    """
    notes: list[str] = []
    chosen_model = ""
    cleaned = model.strip()
    if cleaned and cleaned.lower() not in INHERIT_MODELS:
        if not allow_model:
            notes.append(UNTRUSTED_MODEL_NOTE.format(model=cleaned))
        elif "/" in cleaned:
            chosen_model = cleaned
        else:
            notes.append(
                f"model '{cleaned}' tanınmadı (biçim <sağlayıcı>/<model>); "
                "oturum modeli kullanılacak"
            )
    chosen_effort: ReasoningEffort | None = None
    wanted = effort.strip().lower()
    if wanted:
        try:
            chosen_effort = ReasoningEffort(wanted)
        except ValueError:
            known = ", ".join(item.value for item in ReasoningEffort)
            notes.append(f"effort '{effort.strip()}' tanınmadı ({known}); oturum eforu kalır")
    choice = TurnModelChoice(chosen_model, chosen_effort)
    if chosen_model:
        notes.append(f"bu tur model: {chosen_model}")
    if chosen_effort is not None:
        notes.append(f"bu tur efor: {chosen_effort.value}")
    return TurnModelResolution(choice, tuple(notes))
