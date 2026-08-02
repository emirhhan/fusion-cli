"""`/level` ve `/development` akışları — seç, uygula, kalıcılaştır.

Komut işleyicileri ince kalsın diye akış buraya alınmıştır (RULES.md "UI ve CLI":
bir komut fonksiyonu 40 satırı aşmaz, mantık aşağı katmana taşınır).

Seçim ekranı ve katalog DIŞARIDAN geçirilir. İkisi de gerçek dünyaya bakar (terminal
ve ağ); enjekte edilmeseler bu akışlar ancak canlı terminal ve canlı ağ ile test
edilebilirdi.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...config import model_select, writer
from ...config.eligibility import eligible_profiles
from ...config.models import Config, ProfileEligibility
from ...core.errors import ConfigError
from ...core.model_capability import ModelCapability, ToolSupport
from ...providers import catalog
from ...providers.catalog import CatalogEntry
from ...ui import messages
from ...ui.picker import Choice, pick

#: Seçim ekranı imzası: seçenekler + başlık → seçilen değer (vazgeçilirse None).
Picker = Callable[..., str | None]

#: Serbest metin sorma imzası (özel model alias'ı için).
TextAsker = Callable[[str], str | None]

#: Katalog getirici imzası. Ağ hatasında boş demet döner, istisna fırlatmaz.
CatalogFetcher = Callable[[], tuple[CatalogEntry, ...]]


@dataclass(frozen=True, slots=True)
class FlowResult:
    """Bir akışın sonucu: yeni yapılandırma (değiştiyse) ve gösterilecek metin."""

    config: Config
    message: str


@dataclass(frozen=True, slots=True)
class Source:
    """`/development` altındaki bir model kaynağı."""

    key: str
    label: str
    #: Canlı katalog getirici. `None` ise kaynak serbest metin ister (özel model).
    fetcher: CatalogFetcher | None
    description: str = ""
    #: Seçim ücretlendirilir mi? Kullanıcı uyarılır.
    paid: bool = False


def sources() -> tuple[Source, ...]:
    """`/development` kaynakları — kullanıcının istediği sırayla.

    Sıra anlamlıdır ve ücretsiz olanlar öndedir: ürünün varsayılan yolu ücretsizdir,
    ücretli seçenek bilinçli bir adım olmalıdır.
    """
    return (
        Source(
            "openrouter-free",
            messages.DEV_SOURCE_OPENROUTER_FREE,
            catalog.fetch_openrouter_free,
        ),
        Source("nim-free", messages.DEV_SOURCE_NIM_FREE, catalog.fetch_nim),
        Source(
            "openrouter-paid",
            messages.DEV_SOURCE_OPENROUTER_PAID,
            catalog.fetch_openrouter_paid,
            paid=True,
        ),
        Source(
            "custom",
            messages.DEV_SOURCE_CUSTOM,
            None,
            description=messages.DEV_SOURCE_CUSTOM_HINT,
        ),
    )


# --------------------------------------------------------------------------- #
# /level
# --------------------------------------------------------------------------- #


def choose_level(config: Config, *, picker: Picker = pick) -> FlowResult:
    """Kademe seçtir, uygula ve kaydet.

    Kaydetme başarısız olsa bile kademe UYGULANMIŞ kalır: kullanıcı seçimini
    oturum boyunca kullanabilmeli, dosya izni sorunu turu engellememeli.
    """
    picked = picker(
        tuple(Choice(tier.name, tier.name, tier.label) for tier in config.tiers),
        title=messages.LEVEL_TITLE,
        gradient_rows=True,
    )
    if picked is None:
        return FlowResult(config, messages.PICKER_CANCELLED)
    return applied_result(model_select.apply_tier(config, picked), picked)


#: `/mode` seçim ekranındaki "auto" seçeneğinin değeri. Kademe adı DEĞİLDİR:
#: komut işleyicisi bunu görürse profili kademe yerine auto kipine alır.
AUTO_CHOICE = "auto"


def choose_mode(config: Config, *, picker: Picker = pick) -> str | None:
    """Çalışma profili seçtir: auto + tanımlı kademeler.

    Seçilen değeri HAM döndürür (kademe adı ya da `AUTO_CHOICE`); uygulama kararını
    komut işleyicisi verir, çünkü `auto` bir yapılandırma değişikliği değil oturum
    kipidir ve `FlowResult` (config değişimi) kalıbına girmez. Vazgeçilirse `None`.
    """
    auto = Choice(AUTO_CHOICE, messages.MODE_AUTO_LABEL, messages.MODE_AUTO_HINT)
    kademeler = tuple(Choice(tier.name, tier.name, tier.label) for tier in config.tiers)
    return picker((auto, *kademeler), title=messages.MODE_TITLE, gradient_rows=True)


def applied_result(config: Config, tier_name: str) -> FlowResult:
    """Uygulanmış kademeyi kalıcılaştır ve sonucu anlat.

    Seçim ekranından da (`choose_level`) betiklenebilir yoldan da (`/level premium`)
    aynı fonksiyon geçer; iki yol ayrı yazılsaydı biri kaydetmeyi unutabilirdi.
    """
    applied = messages.LEVEL_APPLIED.format(name=tier_name, model=config.agent.model)
    return FlowResult(config, f"{applied}\n{_persist(config)}")


# --------------------------------------------------------------------------- #
# /development
# --------------------------------------------------------------------------- #


def choose_development(
    config: Config, *, picker: Picker = pick, ask_text: TextAsker | None = None
) -> FlowResult:
    """Kaynak seç → model seç → uygula ve kaydet.

    Seçilen model agent, hakem ve havuzun TAMAMINA uygulanır: kullanıcı tek bir
    model seçtiğini söylüyor, rollerden birinin eski modelde kalması sürpriz olurdu.
    """
    source = _choose_source(picker)
    if source is None:
        return FlowResult(config, messages.PICKER_CANCELLED)

    model_id, reason = _choose_model(
        source, picker=picker, ask_text=ask_text, eligibility=config.profile_eligibility
    )
    if model_id is None:
        return FlowResult(config, reason)

    try:
        updated = model_select.apply_single_model(config, model_id)
    except ConfigError as error:
        return FlowResult(config, str(error))

    lines = [messages.DEV_APPLIED.format(model=model_id)]
    if source.paid:
        lines.append(messages.DEV_PAID_WARNING)
    lines.append(_persist(updated))
    return FlowResult(updated, "\n".join(lines))


def _choose_source(picker: Picker) -> Source | None:
    available = sources()
    picked = picker(
        tuple(Choice(item.key, item.label, item.description) for item in available),
        title=messages.DEV_SOURCE_TITLE,
    )
    return next((item for item in available if item.key == picked), None)


def _choose_model(
    source: Source,
    *,
    picker: Picker,
    ask_text: TextAsker | None,
    eligibility: dict[str, ProfileEligibility],
) -> tuple[str | None, str]:
    """Kaynağa göre modeli belirle: katalogdan seç ya da serbest metin al.

    Model seçilemediğinde SEBEBİ de döner. Katalog boş kaldığında "vazgeçildi"
    demek ağın ya da anahtarın eksik olduğunu gizler; kullanıcı komutu bozuk sanar.
    """
    if source.fetcher is None:
        return _ask_custom(ask_text), messages.PICKER_CANCELLED
    entries = source.fetcher()
    if not entries:
        return None, messages.DEV_EMPTY_CATALOG
    picked = picker(
        tuple(
            Choice(entry.model_id, entry.model_id, _model_label(entry, eligibility))
            for entry in entries
        ),
        title=messages.DEV_MODEL_TITLE.format(source=source.label),
    )
    return picked, messages.PICKER_CANCELLED


def _ask_custom(ask_text: TextAsker | None) -> str | None:
    if ask_text is None:
        return None
    answer = ask_text(messages.DEV_CUSTOM_PROMPT)
    return answer.strip() if answer and answer.strip() else None


def catalog_capability(entry: CatalogEntry) -> ModelCapability:
    """Katalog kaydından yeteneği türet.

    Katalog yalnızca bağlam penceresini VERİR; araç desteği ve reasoning
    doğrulanmamıştır (`UNKNOWN`). Uydurulmaz: bilinen tek gerçek sinyal bağlamdır.
    """
    return ModelCapability(tool_support=ToolSupport.UNKNOWN, context_window=entry.context_length)


def _model_label(entry: CatalogEntry, eligibility: dict[str, ProfileEligibility]) -> str:
    """Seçim satırının açıklaması: bağlam + uygun olduğu profiller.

    Rozet, hangi profillerin bu modeli ÖNERDİĞİNİ gösterir; kullanıcı bir modelin
    neden bir profile uygun olmadığını (küçük bağlam) satırda görebilir.
    """
    parts = [_context_label(entry)]
    profiles = eligible_profiles(catalog_capability(entry), eligibility)
    if profiles:
        parts.append(messages.DEV_PROFILE_BADGE.format(profiles="·".join(profiles)))
    return "  ·  ".join(part for part in parts if part)


def _context_label(entry: CatalogEntry) -> str:
    """Bağlam uzunluğu seçimin en ayırt edici bilgisidir; bilinmiyorsa yazılmaz."""
    return f"{entry.context_length:,} token".replace(",", ".") if entry.context_length else ""


# --------------------------------------------------------------------------- #


def _persist(config: Config) -> str:
    """Seçimi kalıcılaştır. Yazamamak akışı bozmaz, yalnızca bildirilir."""
    try:
        return messages.LEVEL_SAVED.format(path=writer.write_model_section(config))
    except ConfigError as error:
        return messages.LEVEL_SAVE_FAILED.format(error=error)
