"""Masaüstü composer'ındaki kademe (düşünme düzeyi) seçicisi.

Kademe merdiveni yapılandırmada zaten tanımlıdır (`config.tiers`) ve
`config.model_select.apply_tier` onu uygular; TUI yıllardır bunu kullanıyor.
Bu modül YENİ bir kavram getirmez, var olanı masaüstü protokolüne açar.

Sağlayıcı kilidi: kademelerin baş modelleri NVIDIA'da barınır. Kullanıcı
sağlayıcı tercihini NVIDIA'yı dışlayacak biçimde ayarladıysa kademe seçmek
anlamsızdır — seçim sessizce yok sayılmak yerine AÇIKÇA kilitlenir ve gerekçesi
bildirilir. Kararı istemci tahmin etmez; buradan gelir.
"""

from __future__ import annotations

from typing import Any

from ..config.keys import ProviderPreference
from ..config.model_select import apply_tier
from ..config.models import Config
from ..core.errors import ConfigError

#: Kilitliyken arayüzün göstereceği gerekçe.
LOCKED_REASON = (
    "Kademe seçimi NVIDIA sağlayıcısıyla çalışır; etkin sağlayıcı değiştirilmeden düzenlenemez."
)

_NO_TIERS = "Bu yapılandırmada tanımlı kademe yok."


def is_editable(config: Config) -> bool:
    """Kademe seçilebilir mi?

    `AUTO` da düzenlenebilirdir: varsayılan zincir NVIDIA'yı içerir, yalnızca
    NVIDIA'yı DIŞLAYAN açık bir tercih kilitler.
    """
    try:
        preference = ProviderPreference(str(config.runtime.provider).strip().lower())
    except ValueError:
        # Geçersiz tercih yapılandırma katmanında zaten hata verir; burada
        # kilitlemek, bilinmeyen bir değerde sessizce NVIDIA varsaymaktan iyidir.
        return False
    return preference is not ProviderPreference.OPENROUTER


def active_tier_name(config: Config) -> str:
    """Etkin kademe: agent modelini taşıyan kademe. Eşleşme yoksa ilk kademe."""
    for tier in config.tiers:
        if tier.agent.model == config.agent.model:
            return tier.name
    return config.tiers[0].name if config.tiers else ""


def list_tiers(config: Config) -> dict[str, Any]:
    """`kademe.listele`: kademeler, etkin olan ve düzenlenebilirlik."""
    if not config.tiers:
        return {"ok": False, "metin": _NO_TIERS}
    editable = is_editable(config)
    return {
        "ok": True,
        "kademeler": [
            {"ad": tier.name, "etiket": tier.label, "model": tier.agent.model}
            for tier in config.tiers
        ],
        "etkin": active_tier_name(config),
        "duzenlenebilir": editable,
        "metin": "" if editable else LOCKED_REASON,
    }


def select_tier(config: Config, data: dict[str, Any]) -> tuple[Config, dict[str, Any]]:
    """`kademe.sec`: kademeyi uygula. Yeni yapılandırma ve yanıtı birlikte döner.

    `Config` frozen olduğu için yeni nesne döndürülür; çağıran onu duruma yazar.
    Başarısızlıkta yapılandırma DEĞİŞMEZ — yarım uygulanmış bir kademe agent ile
    hakemi ayrı seviyelerde bırakırdı.
    """
    if not is_editable(config):
        return config, {"ok": False, "metin": LOCKED_REASON}
    name = data.get("ad")
    if not isinstance(name, str) or not name.strip():
        return config, {"ok": False, "metin": "Kademe adı verilmedi."}
    try:
        updated = apply_tier(config, name.strip())
    except ConfigError as hata:
        return config, {"ok": False, "metin": str(hata)}
    return updated, {
        "ok": True,
        "etkin": active_tier_name(updated),
        "model": updated.agent.model,
        "hakem": updated.judge.model,
    }
