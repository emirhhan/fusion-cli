"""Seçili model dosya yazamıyorsa işi o tur için çırak API modeline devret.

Hedef mimari: web modelleri (ChatGPT/Gemini web) öğretmendir, işi araç
kullanmada güvenilir ücretsiz API çırağı yapar. Ölçüldü (30 Eylül, masaüstü):
kullanıcı ChatGPT web'i seçmişken "klasör oluştur" isteğinde yazma araçları
hiç sunulmadı ve model kodu sohbete döktü.

Devir TUR KAPSAMLIDIR: yapılandırma değişmez (kullanıcının seçimi kalıcı olarak
kendiliğinden değiştirilmez, bkz. `config/model_select.py`). Seçili web modeli,
giriş doğrulanmışsa ve ayrı bir öğretmen tanımlı değilse o tur öğretmen olur.
"""

from __future__ import annotations

from dataclasses import replace

from ...config.model_select import APPRENTICE_TIER_NAME
from ...config.models import Config
from ...config.tool_policy import mutation_policy_for_model
from ...core.types import ModelSpec


def apprentice_spec(config: Config) -> ModelSpec | None:
    """Çırak kademesinin baş modeli; yoksa ya da o da yazamıyorsa None."""
    tier = config.tier_by_name(APPRENTICE_TIER_NAME)
    if tier is None or not mutation_policy_for_model(config, tier.agent.model).ok:
        return None
    # `strict` çıkarılır: çırak zinciri yedeğe geçebilmeli (akış kırılmaz).
    return replace(tier.agent, tags=tuple(tag for tag in tier.agent.tags if tag != "strict"))


def teacher_for_turn(config: Config, selected: ModelSpec) -> ModelSpec | None:
    """Bu turun öğretmeni: tanımlı öğretmen, yoksa giriş doğrulanmış seçili web modeli."""
    if config.teacher is not None:
        return config.teacher
    verified = any(
        session.model == selected.model
        and session.transport == "browser"
        and session.enabled
        and session.login_verified
        for session in config.web_sessions
    )
    return ModelSpec(name="ogretmen", model=selected.model) if verified else None
