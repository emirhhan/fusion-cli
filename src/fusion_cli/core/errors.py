"""Proje hata hiyerarşisi.

Tüm proje hataları tek bir kökten (`FusionError`) türer; böylece sınır katmanları
(CLI giriş noktası) "bizim bildiğimiz bir hata mı, beklenmedik bir çökme mi"
ayrımını tip üzerinden yapabilir.

Not: Sağlayıcı 429 verdi / model yanıt vermedi gibi BEKLENEN başarısızlıklar hata
fırlatmaz; `ModelResult(ok=False)` ile taşınır (bkz. `core.types`). Burada yalnızca
akışın devam edemeyeceği durumlar bulunur.

Yeni hata tipleri, gerçekten fırlatıldıkları fazda eklenir.
"""

from __future__ import annotations


class FusionError(Exception):
    """Fusion-CLI'ın bilerek fırlattığı tüm hataların kökü."""


class ConfigError(FusionError):
    """Yapılandırma okunamadı, doğrulanamadı ya da bilinmeyen anahtar içeriyor."""


class ProviderError(FusionError):
    """LLM sağlayıcı katmanı hiç kurulamadı (ör. tanımlı model yok)."""


class PathAccessError(FusionError):
    """Kısıtlı kipte proje kökü dışına çıkan bir dosya yoluna erişilmek istendi."""


class EvalError(FusionError):
    """Değerlendirme seti okunamadı, doğrulanamadı ya da geçersiz ölçüt içeriyor."""


class KnowledgeError(FusionError):
    """Ortak bilgi paketi işlenemedi (ör. imza için gerekli bağımlılık yok)."""
