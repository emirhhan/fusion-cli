"""Ham içerik taşımayan istem ölçüm sözleşmeleri."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstructionMeasurement:
    """İlk yükleyicinin dosya ölçümü; mutlak yol veya içerik saklanmaz."""

    label: str
    layer: str
    chars: int
    trimmed_chars: int


@dataclass(frozen=True, slots=True)
class PromptTransportMeasurement:
    """Gerçek gönderim sınırında ölçülen karakterler; token değildir."""

    input_chars: int
    sent_chars: int
    trimmed_chars: int
    attachment_chars: int = 0


@dataclass(frozen=True, slots=True)
class PromptManifest:
    """Üst toplam ayrık parçalardır; repo/skill talimat system altkırılımıdır."""

    system_chars: int
    history_chars: int
    tool_chars: int
    total_chars: int
    repo_map_chars: int = 0
    skill_chars: int = 0
    instruction_files: tuple[InstructionMeasurement, ...] = ()
    instruction_trimmed_chars: int = 0
    instruction_notes: tuple[str, ...] = ()
    transport: PromptTransportMeasurement | None = None
    model: str = ""
    profile: str | None = None
    tokens_estimated: bool = True
    prompt_tokens: int = 0
    subcomponents_in_system: bool = True


@dataclass(frozen=True, slots=True)
class ContextProfile:
    """Yalnız açık model/sağlayıcı eşleşmesinde kullanılan karakter eşiği."""

    name: str
    provider: str
    model: str
    compression_chars: int

    def __post_init__(self) -> None:
        if not self.name or not self.provider or not self.model:
            raise ValueError("Bağlam profili ad, sağlayıcı ve model gerektirir.")
        if type(self.compression_chars) is not int or self.compression_chars <= 0:
            raise ValueError("Bağlam profili pozitif karakter eşiği gerektirir.")
