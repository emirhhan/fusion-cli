"""Oturum içi model değiştirme.

`Config` ve `ModelSpec` frozen'dır: mutasyon yoktur, her işlem YENİ bir yapılandırma
döndürür. Bu sayede yarım kalmış bir değişiklik oturumu bozamaz ve fonksiyonlar
saftır — ağ, dosya ya da yan etki olmadan test edilir.

Değişiklik yalnızca oturum boyunca yaşar; kalıcı olması için `config.yaml`'a yazılır.
"""

from __future__ import annotations

from dataclasses import replace

from ..core.errors import ConfigError
from ..core.types import ModelSpec
from .eligibility import capability_from_spec
from .models import Config
from .tool_policy import can_be_mutation_agent


def select_agent_spec(config: Config, task_type: str) -> ModelSpec:
    """Agent turunda kullanılacak modeli görev tipine göre seç.

    `task_model_map` uzun süre yalnızca fusion motorunda uygulanıyordu; agent her
    zaman `agent:` rolünü kullanıyordu. Yani haritada "code" için başka bir model
    yazmak agent modunda hiçbir şey değiştirmiyor, yapılandırma yalan söylüyordu.

    Haritada karşılık yoksa ya da yazan ad tanımlı bir aday değilse `agent:` rolüne
    düşülür: yapılandırmadaki bir yazım hatası turu çökertmez.
    """
    mapped = config.task_model_map.get(task_type)
    if not mapped:
        return config.agent
    secilen = config.candidate_by_name(str(mapped))
    if secilen is None:
        return config.agent
    # Araç desteği olmayan (ya da yalnızca taklit) bir aday, dosya değiştiren agent
    # OLAMAZ (master prompt §5.3). Böyle bir adaya yönlendirilmişse varsayılan `agent:`
    # rolüne düşülür — o rol araç yetenekli olacak biçimde seçilmiştir.
    if not can_be_mutation_agent(capability_from_spec(secilen)).ok:
        return config.agent
    return _with_agent_fallbacks(secilen, config.agent)


def _with_agent_fallbacks(secilen: ModelSpec, agent: ModelSpec) -> ModelSpec:
    """Aday spec'ini `agent:` rolünün yedek zinciriyle güçlendir.

    Yönlendirme BİRİNCİL modeli değiştirir; dayanıklılığı düşürmemeli. Gerçek hata:
    `agent:` rolüne yedek zinciri yazılmıştı ama tur `task_model_map` üzerinden
    ADAY spec'ini kullanıyor ve adayların yedeği yoktu. Model 429 alınca tur
    bitiyordu — kullanıcı "kotam bitti" sanıyor, oysa NVIDIA NIM'de hız sınırı
    MODEL BAŞINADIR (ölçüldü) ve zincirdeki başka bir model çalışıyor.

    Sıra korunur ve tekrarlar atılır: adayın kendi yedekleri önce gelir, ardından
    agent rolününkiler eklenir.
    """
    ek = tuple(model for model in agent.models if model not in secilen.models)
    if not ek:
        return secilen
    return replace(secilen, fallback=(*secilen.fallback, *ek))


def apply_tier(config: Config, name: str) -> Config:
    """Bir kademeyi uygula: agent, hakem ve aday havuzunu BİRLİKTE değiştir.

    Kademe seçmek "motorun tamamını o seviyeye al" demektir; bu yüzden agent turunu
    yönlendiren `task_model_map` de kademenin BAŞ modeline (agent rolü) bağlanır.

    Eskiden harita eski adı yeni havuzda da bulursa KORUYORDU. Bu sessiz bir hataydı:
    `ultra` seçip sonra `premium`'a geçen kullanıcıda `nemotron-ultra` premium
    havuzunda da bulunduğu için harita ona yapışıyordu — agent rolü `glm-5.2` (premium'un
    baş modeli) olmasına rağmen agent turu `nemotron-ultra` çalıştırıyordu. Kullanıcı
    premium seçip başka modelin cevap verdiğini görüyordu. Kademe artık haritayı
    koşulsuz baş modele bağlar: seçim ekranda ne yazıyorsa tur onu çalıştırır.
    """
    tier = config.tier_by_name(name)
    if tier is None:
        known = ", ".join(item.name for item in config.tiers)
        raise ConfigError(f"'{name}' adlı kademe yok. Tanımlı kademeler: {known}")
    known_names = {candidate.name for candidate in tier.candidates}
    # Baş model kademenin `agent` rolüdür; havuzda karşılığı yoksa (savunmacı)
    # ilk adaya düşülür — `select_agent_spec` yalnızca tanımlı bir adayı bulabilir.
    headline = tier.agent.name if tier.agent.name in known_names else tier.candidates[0].name
    task_model_map = dict.fromkeys(config.task_model_map, headline)
    return replace(
        config,
        agent=tier.agent,
        judge=tier.judge,
        candidates=tier.candidates,
        task_model_map=task_model_map,
    )


#: `/development` ile seçilen tek modelin havuzdaki adı.
SINGLE_MODEL_NAME = "secilen"


def apply_single_model(config: Config, model_id: str) -> Config:
    """Tek bir modeli agent, hakem ve havuzun TAMAMINA uygula.

    `/development` kullanıcıya "şu modelle çalış" dedirtir; rollerden birinin eski
    modelde kalması sürpriz olurdu. Havuz tek adaya iner: aynı modeli üç kez
    paralel sormak fusion'a hiçbir şey katmaz, yalnızca kota yakar.
    """
    spec = ModelSpec(name=SINGLE_MODEL_NAME, model=_validated(model_id))
    return replace(
        config,
        agent=spec,
        judge=spec,
        candidates=(spec,),
        # Harita yalnızca tanımlı bir adayı işaret edebilir; havuz tek adaya
        # indiği için her görev tipi ona bağlanır.
        task_model_map=dict.fromkeys(config.task_model_map, SINGLE_MODEL_NAME),
    )


def set_agent_model(config: Config, model_id: str) -> Config:
    """Agent rolünün modelini değiştir."""
    return replace(config, agent=replace(config.agent, model=_validated(model_id)))


def set_judge_model(config: Config, model_id: str) -> Config:
    """Hakem (ve sentez) rolünün modelini değiştir."""
    return replace(config, judge=replace(config.judge, model=_validated(model_id)))


def set_candidate_model(config: Config, key: str, model_id: str) -> Config:
    """Bir fusion adayının modelini değiştir. `key`: aday adı ya da 1-tabanlı sıra."""
    index = resolve_candidate(config, key)
    candidates = list(config.candidates)
    candidates[index] = replace(candidates[index], model=_validated(model_id))
    return replace(config, candidates=tuple(candidates))


def add_candidate(config: Config, name: str, model_id: str, tags: tuple[str, ...] = ()) -> Config:
    """Havuza yeni aday ekle."""
    if config.candidate_by_name(name) is not None:
        raise ConfigError(f"'{name}' adlı aday zaten var.")
    spec = ModelSpec(name=name, model=_validated(model_id), tags=tags)
    return replace(config, candidates=(*config.candidates, spec))


def remove_candidate(config: Config, name: str) -> Config:
    """Havuzdan aday çıkar. Son aday çıkarılamaz — fusion en az bir modele ihtiyaç duyar."""
    if config.candidate_by_name(name) is None:
        raise ConfigError(f"'{name}' adlı aday yok.")
    if len(config.candidates) <= 1:
        raise ConfigError("En az bir aday kalmalı.")
    remaining = tuple(item for item in config.candidates if item.name != name)
    return replace(config, candidates=remaining)


def resolve_candidate(config: Config, key: str) -> int:
    """Aday adını ya da 1-tabanlı sırasını 0-tabanlı indekse çevir."""
    wanted = key.strip()
    if wanted.isdigit():
        index = int(wanted) - 1
        if not 0 <= index < len(config.candidates):
            raise ConfigError(f"Aday sırası aralık dışı: {wanted}")
        return index
    for index, candidate in enumerate(config.candidates):
        if candidate.name == wanted:
            return index
    known = ", ".join(item.name for item in config.candidates)
    raise ConfigError(f"'{wanted}' adlı aday yok. Tanımlı adaylar: {known}")


def format_models(config: Config) -> str:
    """Etkin modelleri tek metinde özetle."""
    lines = [f"agent : {config.agent.model}", f"hakem : {config.judge.model}", "adaylar:"]
    for index, candidate in enumerate(config.candidates, 1):
        tags = f"  [{', '.join(candidate.tags)}]" if candidate.tags else ""
        lines.append(f"  {index}. {candidate.name}: {candidate.model}{tags}")
    return "\n".join(lines)


def _validated(model_id: str) -> str:
    """Model kimliği `<sağlayıcı>/<model>` biçiminde olmalıdır."""
    cleaned = model_id.strip()
    if "/" not in cleaned:
        raise ConfigError(
            f"Geçersiz model kimliği: '{cleaned}'. Biçim: <sağlayıcı>/<model> "
            "(ör. openrouter/openai/gpt-oss-20b:free). Liste için: fusion models --fetch"
        )
    return cleaned
