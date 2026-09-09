"""Görev gereksinimini kalıcı sağlayıcı kanıtlarıyla eşleştirir."""

from __future__ import annotations

from dataclasses import dataclass

from ..config.eligibility import capability_from_spec
from ..config.models import WebSessionConfig
from ..core.errors import ConfigError
from ..core.model_capability import ToolSupport
from ..core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class TaskRequirements:
    tools: bool = False
    native_tools: bool = False
    images: bool = False
    web: bool = False
    long_running: bool = False
    exclusive_session: bool = False


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    tools: bool
    native_tools: bool
    images: bool
    web: bool
    long_running: bool
    exclusive_session: bool
    evaluation_state: str = "unknown"
    last_evaluated_at: float = 0.0


def capabilities_for(
    spec: ModelSpec, sessions: tuple[WebSessionConfig, ...] = ()
) -> ProviderCapabilities:
    """Yapılandırılmış web oturumu ve model etiketlerinden kanıtlı profil üret."""
    session = next((item for item in sessions if item.enabled and item.model == spec.model), None)
    if session is not None:
        browser = session.transport == "browser"
        emulated = session.tool_support == "emulated" and session.tool_eval_passed
        return ProviderCapabilities(
            tools=emulated,
            native_tools=False,
            images=not browser,
            web=True,
            long_running=not browser,
            exclusive_session=browser,
            evaluation_state="passed" if emulated else "unverified",
        )
    if spec.model.split("/", 1)[0] in {
        "chatgpt_web",
        "claude_web",
        "gemini_web",
        "copilot_web",
    }:
        return ProviderCapabilities(
            tools=True,
            native_tools=False,
            images=False,
            web=True,
            long_running=False,
            exclusive_session=True,
            evaluation_state="legacy",
        )
    capability = capability_from_spec(spec)
    explicitly_unsupported = capability.tool_support is ToolSupport.NONE
    emulated = capability.tool_support is ToolSupport.EMULATED
    return ProviderCapabilities(
        tools=not explicitly_unsupported,
        native_tools=not explicitly_unsupported and not emulated,
        images=capability.vision or "vision" in spec.tags,
        web=capability.tool_support is ToolSupport.NATIVE,
        long_running=True,
        exclusive_session=False,
        evaluation_state="declared"
        if capability.tool_support is not ToolSupport.UNKNOWN
        else "unknown",
    )


def compatibility_issues(
    capabilities: ProviderCapabilities, requirements: TaskRequirements
) -> tuple[str, ...]:
    labels = {
        "tools": "araç desteği",
        "native_tools": "yerel araç çağrısı",
        "images": "görsel desteği",
        "web": "web erişimi",
        "long_running": "uzun çalışma desteği",
        "exclusive_session": "ayrılmış oturum desteği",
    }
    return tuple(
        labels[field]
        for field in labels
        if getattr(requirements, field) and not getattr(capabilities, field)
    )


def select_compatible_model(
    candidates: tuple[ModelSpec, ...],
    requirements: TaskRequirements,
    sessions: tuple[WebSessionConfig, ...] = (),
    *,
    strict: bool = False,
) -> ModelSpec:
    """Zorunlu yetenekleri düşürmeden ilk uyumlu adayı seç."""
    for candidate in candidates:
        if not compatibility_issues(capabilities_for(candidate, sessions), requirements):
            return candidate
    first = candidates[0] if candidates else None
    issues = compatibility_issues(capabilities_for(first, sessions), requirements) if first else ()
    prefix = "Seçilen model" if strict else "Model havuzu"
    detail = ", ".join(issues) or "uygun ve doğrulanmış sağlayıcı yok"
    raise ConfigError(f"{prefix} bu görevle uyumsuz: {detail}.")


def infer_task_requirements(
    task: str, *, has_images: bool = False, mutating: bool = False
) -> TaskRequirements:
    """Model girdisinin gereksinimini çıkar; orkestratör yeteneğini modele yükleme.

    Uzun görevleri planlayıcı, dosya/ağ işlemlerini araçlar yürütür. Görevde
    "oyun yap" geçmesi native function calling gerektirmez; doğrulanmış emülasyon
    aynı araçları çağırabilir. PNG üretmek de modele resim girdisi göndermek değildir.
    Açık taşıma gereksinimleri gerektiğinde TaskRequirements ile ayrıca verilir.
    """
    lowered = task.casefold()
    web = any(word in lowered for word in ("internet", "webden", "web'den", "asset topla"))
    mutation_words = (
        "oluştur",
        "olustur",
        "düzelt",
        "duzelt",
        "değiştir",
        "degistir",
        "ekle",
        "yaz",
        "yap",
        "kur",
    )
    mutating = mutating or any(word in lowered for word in mutation_words)
    return TaskRequirements(
        tools=mutating or web,
        images=has_images,
    )
