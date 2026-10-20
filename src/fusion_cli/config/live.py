"""Canlı yapılandırma yeniden yükleme yardımcıları.

Kontrol paneli ile terminal AYRI süreçlerdir; bu yüzden bellekte tek bir `Config`
nesnesini paylaşamazlar. Bu modül ikisine de aynı ucuz dosya-sürüm kontrolünü verir
ve yapılandırmayı YALNIZCA turlar/istekler arasında yeniden yükler — asla etkin bir
model çağrısının ortasında değil.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .loader import load_config
from .models import Config

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConfigRevision:
    """Etkin kullanıcı yapılandırmasının dosya sistemi sürümü."""

    path: Path | None
    mtime_ns: int = 0
    size: int = 0

    @property
    def value(self) -> str:
        if self.path is None:
            return "defaults"
        return f"{self.mtime_ns:x}-{self.size:x}"


def revision(config: Config) -> ConfigRevision:
    """`config.source` için kararlı, sır içermeyen bir sürüm döndür."""
    source = config.source
    if source is None:
        return ConfigRevision(None)
    try:
        stat = source.stat()
    except OSError:
        return ConfigRevision(source)
    return ConfigRevision(source.resolve(), stat.st_mtime_ns, stat.st_size)


def reload_if_changed(
    config: Config, previous: ConfigRevision | None = None
) -> tuple[Config, ConfigRevision, bool]:
    """Yapılandırma dosyasının sürümü değiştiyse yeniden yükle.

    `previous`'ın sahibi çağırandır. Kaynak kaybolursa ya da başka bir süreç yazarken
    yeni içerik geçici olarak geçersizse, son bilinen-iyi yapılandırma korunur. Atomik
    yazma bu pencereyi seyrek kılar; yine de etkileşimli terminal için güvenli-başarısız
    davranış önemlidir.
    """
    current = revision(config)
    if previous is None:
        return config, current, False
    if current == previous:
        return config, previous, False
    if current.path is None or not current.path.is_file():
        return config, current, False
    try:
        loaded = load_config(current.path)
    except Exception as error:
        # Sınır davranışı: yükleme başarısızsa (yarım yazılmış dosya vb.) son iyi
        # yapılandırmayla devam edilir; sessizce yutulmaz, teşhis için log'lanır.
        _logger.warning("Yapılandırma yeniden yüklenemedi (%s): %s", current.path, error)
        return config, current, False
    return loaded, revision(loaded), True
