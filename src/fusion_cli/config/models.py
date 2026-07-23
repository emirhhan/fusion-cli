"""Tiplenmiş yapılandırma nesneleri.

DİKKAT — bu dosyadaki alanlara varsayılan değer YAZILMAZ. Varsayılanların tek kaynağı
`defaults.yaml`'dır. Eski projede aynı varsayılan hem kodda hem dosyada duruyordu ve
ikisi zamanla ayrıştı (ör. timeout kodda 120, dosyada 45). Alanları zorunlu bırakmak
bu sapmayı derleme/yükleme anında imkânsız kılar: `defaults.yaml` bir alanı unutursa
yapılandırma hiç yüklenmez ve test kırılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Çalışma zamanı davranışı."""

    request_timeout_s: float
    max_retries: int
    temperature: float
    max_tokens: int


@dataclass(frozen=True, slots=True)
class Config:
    """Uygulamanın tüm yapılandırması. Katmanlara ham dict değil bu nesne geçer."""

    agent: ModelSpec
    runtime: RuntimeConfig
    #: Bu yapılandırmanın hangi kullanıcı dosyasından geldiği (yoksa None: yalnız varsayılanlar).
    source: Path | None
