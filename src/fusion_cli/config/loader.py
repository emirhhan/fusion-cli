"""Yapılandırma yükleyici: gömülü varsayılanlar + kullanıcı dosyası → tiplenmiş `Config`.

Akış:
1. `.env` dosyaları yüklenir (yalnızca açık çağrıyla — import anında iş yapılmaz).
2. Pakete gömülü `defaults.yaml` okunur; varsayılanların TEK kaynağıdır.
3. Bulunan ilk kullanıcı yapılandırması bunun üzerine DERİN birleştirilir.
4. Sonuç tiplenmiş dataclass'lara dönüştürülür; bilinmeyen anahtar ya da yanlış tip
   sessizce yutulmaz, anlaşılır bir `ConfigError` verir.

Dönüştürme jeneriktir: dataclass alanlarından türetilir. Yeni bir ayar eklemek için
`defaults.yaml`'a bir satır ve dataclass'a bir alan eklemek yeterlidir; bu dosyaya
dokunulmaz.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import os
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Any, Literal, TypeVar, Union, get_args, get_origin, get_type_hints

import yaml
from dotenv import dotenv_values

from ..core.desktop_settings import DesktopSettings, parse_app_level
from ..core.errors import ConfigError
from ..core.shell_sandbox import SHELL_SANDBOX_MODES
from ..core.types import ModelSpec
from . import trust
from .agent_launch_compat import read_agent_launch
from .agent_launch_settings import AgentLaunchConfig
from .keys import ProviderPreference, apply_preference, detect, prune_config
from .models import (
    BrowserConfig,
    CapabilitiesConfig,
    Config,
    EmbeddingConfig,
    HostedConnectorConfig,
    McpScope,
    McpServerConfig,
    ProfileEligibility,
    RuntimeConfig,
    TierSpec,
    WebSessionConfig,
)
from .paths import (
    ENV_CONFIG,
    ENV_HOME,
    bundled_defaults,
    credentials_file,
    env_file_candidates,
    memory_dir,
    user_config_candidates,
    user_config_dir,
    web_profile_dir,
)
from .sandbox_config import SandboxConfig, validate_sandbox

_logger = logging.getLogger(__name__)

#: Yapılandırmanın en üst düzeyinde izin verilen bölümler.
_SECTIONS = (
    "agent",
    "candidates",
    "extra_candidates",
    "judge",
    "vision",
    "teacher",
    "task_model_map",
    "runtime",
    "embedding",
    "tiers",
    "profile_eligibility",
    "hosted_connectors",
    "mcp_servers",
    "web_sessions",
    "browser",
    "capabilities",
    "sandbox",
    "desktop",
    "agent_launch",
)

# PEP 695 sözdizimi yerine TypeVar: paket Python 3.11'i de destekler.
T = TypeVar("T")

# `.env`'den süreç ortamına bizim eklediğimiz anahtarlar. `load_config` bunları
# süreç ortamında AÇIKÇA verilmiş değerlerden ayırmak için okur: `doctor` gibi
# önce `load_environment` çağıran yollarda `.env`'deki göreli `FUSION_CONFIG`
# zorunlu sayılıp sağlam kurulumu "hazır değil" gösteriyordu (11 Ekim).
_DOTENV_KEYS: frozenset[str] = frozenset()


def load_environment() -> None:
    """`.env` dosyalarını sırayla yükle. Önce yüklenen kazanır; mevcut ortam ezilmez.

    BOŞ değerler atlanır. `load_dotenv` boş string'i de bir değer sayar; proje
    kökündeki şablon `.env` (`OPENROUTER_API_KEY=`) önce yüklendiği için
    kullanıcının `~/.config/fusion-cli/.env` içine girdiği gerçek anahtarı kalıcı
    olarak gölgeliyordu — kurulum "tamam" diyor, hiçbir model çağrılamıyordu.
    Doldurulmamış bir satır "bu anahtar yok" demektir, "bu anahtar boş" değil.
    """
    global _DOTENV_KEYS
    eklenen: set[str] = set()
    for candidate in env_file_candidates():
        if not candidate.is_file():
            continue
        for key, value in dotenv_values(candidate).items():
            # Mevcut ortamda BOŞ dışa aktarılmış değişken (`OPENROUTER_API_KEY=""`) "yok"
            # sayılır: aksi hâlde `.env`'deki gerçek anahtarı gölgeliyordu (`_apply_stored_secrets`
            # boşları zaten böyle ele alıyor; L2-19).
            if value and value.strip() and not os.environ.get(key, "").strip():
                os.environ[key] = value
                eklenen.add(key)
    _DOTENV_KEYS = _DOTENV_KEYS | eklenen
    _apply_stored_secrets()


def _apply_stored_secrets() -> None:
    """Şifreli sır deposundaki değerleri ortama uygula (`.env`'den SONRA).

    `.env` önce yüklenir ve doldurulmuş bir değişkene depo dokunmaz: kullanıcının
    açıkça verdiği değer kazanır. Depo anahtarı (FUSION_SECRET_KEY) yoksa ya da dosya
    çözülemezse sessizce geçilir — sır deposu bir kolaylıktır, uygulamayı engellemez.
    """
    from .credentials import FernetSecretStore
    from .keys import secret_key

    store = FernetSecretStore(credentials_file(), secret_key=secret_key())
    if not store.available:
        return
    try:
        # Eski (SHA-256) dosya ilk açılışta scrypt biçimine taşınır; başarısızlık açılışı
        # engellemez, eski dosya okunmaya devam eder (L2-27).
        store.upgrade_format()
        store.apply_to_environ(os.environ)
    except (ConfigError, OSError):
        # Bozuk dosya / yanlış anahtar: sır uygulanamaz ama uygulama açılmaya devam eder.
        return


def _preference(config: Config) -> ProviderPreference:
    """Yapılandırmadaki sağlayıcı tercihini çöz. Tanınmayan değer hata verir:
    sessizce `auto`ya düşmek, kullanıcının kotasını koruduğunu sanmasına yol açardı."""
    try:
        return ProviderPreference(config.runtime.provider.strip().lower())
    except ValueError as exc:
        gecerli = ", ".join(item.value for item in ProviderPreference)
        raise ConfigError(
            f"Bilinmeyen sağlayıcı tercihi: {config.runtime.provider!r}. Geçerli: {gecerli}"
        ) from exc


def load_config(path: str | Path | None = None) -> Config:
    """Yapılandırmayı yükle ve doğrula.

    `path` verilirse yalnızca o dosya kullanıcı yapılandırması sayılır.
    """
    # FUSION_CONFIG süreç ortamında AÇIKÇA verildiyse o dosya ZORUNLUDUR. Ölçüldü
    # (27 Eylül): yol silinmiş bir geçici dosyayı gösterirken Fusion sessizce
    # kullanıcı config'ine düştü ve kullanıcı farklı bir modelle çalıştığını fark
    # etmedi. `.env`'den gelen değer ise yalnız bir adaydır: kullanıcıların
    # `.env`'inde göreli `config.yaml` duruyor ve başka dizinde yok sayılmalı.
    from_env = None if ENV_CONFIG in _DOTENV_KEYS else os.environ.get(ENV_CONFIG)
    # `.env` yüklenmeden ÖNCE: proje `.env`'i FUSION_CONFIG/FUSION_HOME/XDG_CONFIG_HOME
    # ile config yolunu kendi dosyasına çevirip güven denetimini atlatamasın.
    owned = _user_owned_configs()
    load_environment()

    defaults = _read_yaml(bundled_defaults())
    if path is None and from_env:
        path = from_env
    source = Path(path) if path is not None else _first_existing(user_config_candidates())
    if source is not None:
        if not source.is_file():
            raise ConfigError(f"Yapılandırma dosyası bulunamadı: {source}")
        user = _read_yaml(source)
        _reject_removed(user)
        if path is None:
            user = _restrict_untrusted_project(user, source, owned)
        merged = _deep_merge(defaults, _apply_renames(user))
    else:
        merged = defaults

    try:
        # Kurulu olmayan sağlayıcıların modelleri zincirden düşürülür: NIM anahtarı
        # olmayan kullanıcı her rolde önce başarısız bir çağrı yapıp yedeğe düşerdi.
        yapilandirma = _assemble(merged, source)
        yapilandirma = dataclasses.replace(
            yapilandirma,
            agent_launch=read_agent_launch(
                yapilandirma.agent_launch, home=Path.home(), root=Path.cwd(), environ=os.environ
            ),
        )
        # Proje kökündeki `.mcp.json` (Claude Code biçimi) güvenilen projede eklenir;
        # aynı adda proje kaydı kullanıcı kaydını geçer (P-049).
        yapilandirma = _with_project_mcp_servers(yapilandirma, Path.cwd())
        # Etkin ve çalıştırma onaylı eklentilerin MCP sunucuları (P-059).
        yapilandirma = _with_plugin_mcp_servers(yapilandirma)
        # `--mcp-config` / `--strict-mcp-config` (Claude Code; #253).
        from .mcp_cli import apply_session_mcp

        yapilandirma = apply_session_mcp(yapilandirma)
        # Sıra önemlidir: önce kullanıcının TERCİHİ uygulanır, sonra anahtarı
        # olmayan sağlayıcılar budanır. Tersi olsaydı tercih, budamanın bıraktığı
        # zincire uygulanır ve etkisi kullanıcıya göre değişirdi.
        yapilandirma = apply_preference(yapilandirma, _preference(yapilandirma))
        return prune_config(yapilandirma, detect())
    except ConfigError as exc:
        # Hangi dosyanın suçlu olduğu söylenmezse kullanıcı aramak zorunda kalıyor;
        # dosya birden çok yerde olabiliyor (FUSION_CONFIG, ./, kullanıcı dizini).
        if source is None:
            raise
        raise ConfigError(f"{exc} (dosya: {source})") from exc


#: `.env`'den geldiğinde kullanıcı yapılandırma dizinini başka yere taşıyan değişkenler.
_CONFIG_DIR_ENV = frozenset({"XDG_CONFIG_HOME", "APPDATA"})


def _user_owned_configs() -> frozenset[Path]:
    """Kullanıcının kendi seçtiği config yolları; `.env` yönlendirmesi sayılmaz."""
    owned: list[Path] = []
    if not _DOTENV_KEYS & _CONFIG_DIR_ENV:
        owned.append(user_config_dir() / trust.PROJECT_CONFIG_NAME)
    home = os.environ.get(ENV_HOME)
    if home and ENV_HOME not in _DOTENV_KEYS:
        owned.append(Path(home) / trust.PROJECT_CONFIG_NAME)
    return frozenset(path.resolve() for path in owned)


def _restrict_untrusted_project(
    user: YamlMapping, source: Path, owned: frozenset[Path]
) -> YamlMapping:
    """Kullanıcıya ait olmayan config güvenilmiyorsa yürütme ayarlarını düşür.

    Kullanıcı dizini, süreç ortamındaki FUSION_HOME ve açıkça verilen yol kullanıcının
    seçimidir. `./config.yaml` yedeği yalnız `fusion trust` ile güvenilirse uygulanır;
    proje `.env`'inin gösterdiği başka bir yol hiçbir zaman güvenilir sayılmaz.
    """
    resolved = source.resolve()
    if resolved in owned:
        return user
    cwd = Path.cwd().resolve()
    if resolved == cwd / trust.PROJECT_CONFIG_NAME:
        state = trust.resolve_project_trust(cwd)
    else:
        state = trust.TrustState(False, trust.REASON_REDIRECTED)
    if state.trusted:
        return user
    cleaned, removed = trust.without_execution_settings(user)
    if "agent_launch" in cleaned:
        cleaned = {key: value for key, value in cleaned.items() if key != "agent_launch"}
        removed = (*removed, "agent_launch")
    if removed:
        _logger.warning(
            "Proje yapılandırması (%s) güvenilir değil (%s); şu ayarlar uygulanmadı: %s. "
            "Güveniyorsan: fusion trust",
            source,
            state.reason,
            ", ".join(removed),
        )
    return cleaned


def _assemble(merged: dict[str, object], source: Path | None) -> Config:
    """Birleştirilmiş sözlüğü doğrulayıp `Config` kur."""
    _reject_unknown(merged, _SECTIONS, "yapılandırma kökü")
    web_sessions = _build_web_sessions(merged.get("web_sessions"))
    teacher = (
        _build(ModelSpec, merged["teacher"], "teacher")
        if merged.get("teacher")
        else _verified_web_teacher(web_sessions)
    )
    return Config(
        agent=_build(ModelSpec, merged["agent"], "agent"),
        candidates=_build_candidates(merged["candidates"], merged.get("extra_candidates")),
        judge=_build(ModelSpec, merged["judge"], "judge"),
        # Görme opsiyoneldir: tanımlı değilse görsel kapı hiç kurulmaz.
        vision=_build(ModelSpec, merged["vision"], "vision") if merged.get("vision") else None,
        teacher=teacher,
        task_model_map=_build_task_map(merged["task_model_map"], merged["candidates"]),
        runtime=_build_runtime(merged["runtime"]),
        embedding=_build(EmbeddingConfig, merged["embedding"], "embedding"),
        memory_dir=memory_dir(),
        source=source,
        tiers=_build_tiers(merged["tiers"]),
        profile_eligibility=_build_eligibility(merged.get("profile_eligibility")),
        mcp_servers=_build_mcp_servers(merged.get("mcp_servers")),
        hosted_connectors=_build_hosted_connectors(merged.get("hosted_connectors")),
        web_sessions=web_sessions,
        # Eski kullanıcı dosyasında `browser:` yoksa gömülü varsayılanlar geçerlidir.
        browser=_build(BrowserConfig, merged.get("browser") or {}, "browser"),
        capabilities=_build(CapabilitiesConfig, merged.get("capabilities") or {}, "capabilities"),
        # Eski dosyada `sandbox:` yoksa varsayılan politika (P-010).
        sandbox=validate_sandbox(_build(SandboxConfig, merged.get("sandbox") or {}, "sandbox")),
        desktop=_build_desktop(merged.get("desktop") or {}),
        agent_launch=_build(AgentLaunchConfig, merged.get("agent_launch") or {}, "agent_launch"),
    )


def _build_desktop(raw: object) -> DesktopSettings:
    """`desktop:` bölümü; `app_levels` girdileri yüklemede doğrulanır (çalışma anında değil)."""
    desktop = _build(DesktopSettings, raw, "desktop")
    for entry in desktop.app_levels:
        try:
            parse_app_level(entry)
        except ValueError as error:
            raise ConfigError(f"desktop.app_levels: {error}") from None
    return desktop


def _verified_web_teacher(sessions: tuple[WebSessionConfig, ...]) -> ModelSpec | None:
    """Açık bir öğretmen seçilmediyse doğrulanmış web oturumunu kullan.

    Seçilmiş modeli olan oturum önceliklidir; böylece otomatik web kipindeki
    belirsiz model yerine kullanıcının gerçekten seçtiği model danışılır.
    """
    supported = {"chatgpt_web", "gemini_web"}
    available = [
        session
        for session in sessions
        if session.provider in supported and session.enabled and session.login_verified
    ]
    if not available:
        return None
    selected = next((session for session in available if session.selected_model), available[0])
    return ModelSpec(name="ogretmen", model=selected.model)


def _build_runtime(raw: object) -> RuntimeConfig:
    # YAML 1.1: tırnaksız `off` mantıksal false okunur; kullanıcı niyeti "off"tur.
    if isinstance(raw, dict) and raw.get("shell_sandbox") is False:
        raw = {**raw, "shell_sandbox": "off"}
    runtime = _build(RuntimeConfig, raw, "runtime")
    if runtime.workflow_attempt_calls < 0:
        raise ConfigError("runtime.workflow_attempt_calls: negatif olamaz.")
    # Aralık dışı değerler eskiden sessizce geçiyordu (negatif zaman aşımı, α > 1…; L2-19).
    for name in (
        "request_timeout_s",
        "judge_timeout_s",
        "circuit_cooldown_s",
        "teacher_timeout_s",
        "auto_classifier_timeout_s",
    ):
        if getattr(runtime, name) <= 0:
            raise ConfigError(f"runtime.{name}: sıfırdan büyük olmalı.")
    for name in (
        "max_retries",
        "circuit_failure_threshold",
        "compact_tools_window_tokens",
        "compact_external_tools",
        "tool_output_window",
        "repo_map_chars",
        "instruction_max_chars",
        "skill_index_chars",
        "goal_checkin_minutes",
        "dynamic_workflow_max_concurrent",
        "dynamic_workflow_confirm_agents",
        "agent_team_max_wakes",
    ):
        if getattr(runtime, name) < 0:
            raise ConfigError(f"runtime.{name}: negatif olamaz.")
    if runtime.goal_max_turns < 1:
        raise ConfigError("runtime.goal_max_turns: en az 1 olmalı.")
    for name in ("dynamic_workflow_max_agents", "agent_team_max_members", "agent_team_max_runs"):
        if getattr(runtime, name) < 1:
            raise ConfigError(f"runtime.{name}: en az 1 olmalı.")
    if runtime.desktop_screenshot_max_width < 256:
        raise ConfigError("runtime.desktop_screenshot_max_width: en az 256 piksel olmalı.")
    if runtime.escalation_model.strip() and "/" not in runtime.escalation_model:
        raise ConfigError(
            "runtime.escalation_model: <sağlayıcı>/<model> biçiminde olmalı "
            f"(gelen: {runtime.escalation_model!r}); boş bırakılırsa kademeden otomatik seçilir."
        )
    if runtime.auto_classifier_model.strip() and "/" not in runtime.auto_classifier_model:
        raise ConfigError(
            "runtime.auto_classifier_model: <sağlayıcı>/<model> biçiminde olmalı "
            f"(gelen: {runtime.auto_classifier_model!r}); boş bırakılırsa hakem modeli kullanılır."
        )
    if not 0.0 <= runtime.external_lesson_confidence <= 1.0:
        raise ConfigError("runtime.external_lesson_confidence: 0 ile 1 arasında olmalı.")
    if not 0.0 <= runtime.weak_model_compaction_ratio <= 1.0:
        raise ConfigError("runtime.weak_model_compaction_ratio: 0 ile 1 arasında olmalı.")
    if not 0.0 <= runtime.reliability_alpha <= 1.0:
        raise ConfigError("runtime.reliability_alpha: 0 ile 1 arasında olmalı.")
    if runtime.shell_sandbox not in SHELL_SANDBOX_MODES:
        raise ConfigError(
            f"runtime.shell_sandbox: {runtime.shell_sandbox!r} geçersiz; "
            f"geçerli: {', '.join(SHELL_SANDBOX_MODES)}."
        )
    return runtime


def _build_web_sessions(raw: object) -> tuple[WebSessionConfig, ...]:
    """Web (oturum tabanlı) uç listesini kur. Tanımsız/boşsa özellik kapalı kalır."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"web_sessions: liste bekleniyordu, gelen: {type(raw).__name__}")
    return tuple(
        _without_missing_profile(_build(WebSessionConfig, item, f"web_sessions[{index}]"))
        for index, item in enumerate(raw)
    )


def _without_missing_profile(session: WebSessionConfig) -> WebSessionConfig:
    """Tarayıcı profili diskte yoksa oturumu girişsiz say (dosya değişmez).

    Profil klasörü girişi KANITLAMAZ ama yokluğu girişi kesin çürütür. Ölçüldü
    (11 Ekim): yeni makineye veri dizini taşınmadı, config `login_verified: true`
    dediği için öğretmen girişsiz boş bir tarayıcıyla seçiliyordu.
    """
    from .web_evidence import web_evaluation_matches

    if not web_evaluation_matches(session):
        session = dataclasses.replace(session, tool_eval_passed=False)
    if session.transport != "browser" or not session.login_verified:
        return session
    if web_profile_dir(session.provider, session.account).exists():
        return session
    return dataclasses.replace(session, login_verified=False)


def _build_eligibility(raw: object) -> dict[str, ProfileEligibility]:
    """Profil uygunluk eşiklerini kur: profil adı → `ProfileEligibility`.

    Bölüm tanımsızsa boş sözlük döner: filtre sessizce kapanır, tüm modeller
    gösterilir. Bir profil için eşik yazılırsa jenerik `_build` doğrular.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"profile_eligibility: sözlük bekleniyordu, gelen: {type(raw).__name__}")
    return {
        str(profile): _build(ProfileEligibility, item, f"profile_eligibility.{profile}")
        for profile, item in raw.items()
    }


def _build_hosted_connectors(raw: object) -> tuple[HostedConnectorConfig, ...]:
    """Sağlayıcı-barındırmalı connector listesini oku."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"hosted_connectors: liste bekleniyordu, gelen: {type(raw).__name__}")
    return tuple(
        _build(HostedConnectorConfig, item, f"hosted_connectors[{index}]")
        for index, item in enumerate(raw)
    )


def _with_project_mcp_servers(config: Config, root: Path) -> Config:
    """Güvenilen projenin `.mcp.json` sunucularını kullanıcı kayıtlarına ekle."""
    from .mcp_json import merge_mcp_servers, trusted_project_mcp_servers
    from .mcp_local import disabled_mcp_servers, read_local_mcp_servers

    project_servers = trusted_project_mcp_servers(root)
    local_servers = read_local_mcp_servers(root)
    disabled = disabled_mcp_servers(root)
    if not project_servers and not local_servers and not disabled:
        return config
    merged = merge_mcp_servers(config.mcp_servers, project_servers, local_servers)
    return dataclasses.replace(
        config, mcp_servers=tuple(server for server in merged if server.name not in disabled)
    )


def _with_plugin_mcp_servers(config: Config) -> Config:
    """Eklenti sunucuları (`plugin_<eklenti>_<sunucu>`) kullanıcı/proje adlarını geçmez."""
    from .mcp_local import disabled_mcp_servers
    from .plugin_store import plugin_mcp_servers

    taken = {server.name for server in config.mcp_servers}
    # `/mcp` aç/kapa ile bu projede kapatılan sunucular yüklenmez (Claude disabledMcpServers).
    taken |= disabled_mcp_servers(Path.cwd())
    extra = tuple(server for server in plugin_mcp_servers() if server.name not in taken)
    if not extra:
        return config
    return dataclasses.replace(config, mcp_servers=(*config.mcp_servers, *extra))


def refresh_plugin_mcp_servers(config: Config) -> Config:
    """Eklenti kur/aç/kapat/kaldır sonrası: PLUGIN kapsamlı kayıtları diskteki kayda göre yenile.

    Ölçüldü (31 Ekim): kapatılan ya da kaldırılan eklentinin MCP sunucusu çalışan oturumun
    yapılandırmasında kalıyor, araçları oturum yeniden başlayana dek çağrılabiliyordu.
    """
    others = tuple(s for s in config.mcp_servers if s.scope is not McpScope.PLUGIN)
    return _with_plugin_mcp_servers(dataclasses.replace(config, mcp_servers=others))


def _build_mcp_servers(raw: object) -> tuple[McpServerConfig, ...]:
    """Dış MCP sunucu listesini kur. Tanımsız/boşsa MCP istemcisi hiç kurulmaz."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"mcp_servers: liste bekleniyordu, gelen: {type(raw).__name__}")
    servers = tuple(
        _build(McpServerConfig, item, f"mcp_servers[{index}]") for index, item in enumerate(raw)
    )
    for server in servers:
        for budget in (
            server.connect_timeout_s,
            server.list_timeout_s,
            server.call_timeout_s,
            server.close_timeout_s,
        ):
            if budget is not None and (not math.isfinite(budget) or budget <= 0):
                raise ConfigError("MCP ağ süre sınırları pozitif ve sonlu olmalı.")
        if any(not math.isfinite(delay) or delay <= 0 for delay in server.retry_delays_s or ()):
            raise ConfigError("MCP yeniden deneme aralıkları pozitif ve sonlu olmalı.")
        if server.max_tools is not None and server.max_tools < 1:
            raise ConfigError(
                f"MCP '{server.name}': max_tools en az 1 olmalı (sınırsız için boş bırak)."
            )
    return servers


def _build_tiers(raw: object) -> tuple[TierSpec, ...]:
    """Kademe listesini doğrula: boş olamaz, adlar benzersiz ve küçük harf olmalı.

    Ad benzersizliği şart: `tier_by_name` ilk eşleşeni döndürür, bir ad iki kez
    yazılırsa ikincisi sessizce ölü tanım olurdu.
    """
    if not isinstance(raw, list) or not raw:
        raise ConfigError("tiers: en az bir kademe tanımlı olmalı.")
    specs = tuple(_build(TierSpec, item, f"tiers[{index}]") for index, item in enumerate(raw))
    for spec in specs:
        if spec.name != spec.name.lower():
            raise ConfigError(f"tiers: kademe adı küçük harf olmalı, gelen: '{spec.name}'")
        if not spec.candidates:
            raise ConfigError(f"tiers.{spec.name}: en az bir aday tanımlı olmalı.")
    names = [spec.name for spec in specs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(
            f"tiers: kademe adları benzersiz olmalı, tekrar eden: {', '.join(duplicates)}"
        )
    return specs


def _build_candidates(raw: object, extra: object = None) -> tuple[ModelSpec, ...]:
    """Aday listesini doğrula: boş olamaz, adlar benzersiz olmalı.

    `extra_candidates` havuza EKLER, yerini almaz. Derin birleştirmede bir liste
    tamamen değiştirilir; varsayılanları koruyup yanına yerel bir model (Ollama,
    vLLM) eklemek isteyen kullanıcı için ekleyici bir bölüm gereklidir.
    """
    if not isinstance(raw, list) or not raw:
        raise ConfigError("candidates: en az bir aday tanımlı olmalı.")
    specs = tuple(_build(ModelSpec, item, f"candidates[{index}]") for index, item in enumerate(raw))
    if extra is not None:
        if not isinstance(extra, list):
            raise ConfigError("extra_candidates: liste bekleniyordu.")
        specs += tuple(
            _build(ModelSpec, item, f"extra_candidates[{index}]")
            for index, item in enumerate(extra)
        )
    names = [spec.name for spec in specs]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(
            f"candidates: aday adları benzersiz olmalı, tekrar eden: {', '.join(duplicates)}"
        )
    return specs


def _build_task_map(raw: object, candidates: object) -> dict[str, str]:
    """Görev tipi eşlemesi var olmayan bir adayı işaret edemez."""
    if not isinstance(raw, dict):
        raise ConfigError(f"task_model_map: sözlük bekleniyordu, gelen: {type(raw).__name__}")
    known = {
        item.get("name")
        for item in (candidates if isinstance(candidates, list) else [])
        if isinstance(item, dict)
    }
    mapping: dict[str, str] = {}
    for task_type, name in raw.items():
        if not isinstance(name, str):
            raise ConfigError(f"task_model_map.{task_type}: metin bekleniyordu.")
        if name not in known:
            raise ConfigError(
                f"task_model_map.{task_type}: '{name}' adlı aday tanımlı değil. "
                f"Tanımlı adaylar: {', '.join(sorted(str(k) for k in known))}"
            )
        mapping[str(task_type)] = name
    return mapping


# --------------------------------------------------------------------------- #
# Okuma ve birleştirme
# --------------------------------------------------------------------------- #

# YAML doğası gereği tipsizdir; `Any` yalnızca bu sınırda kullanılır ve aşağıdaki
# `_build` çağrısında tiplenmiş dataclass'lara dönüştürülerek katmanlara öyle geçer.
YamlMapping = dict[str, Any]


def _read_yaml(path: Path) -> YamlMapping:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Yapılandırma okunamadı ({path}): {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Yapılandırma geçerli YAML değil ({path}): {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"Yapılandırma kökü sözlük olmalı ({path}), gelen: {type(raw).__name__}")
    return raw


#: Taşıma sırasında ADI DEĞİŞEN ayarlar: eski ad → yeni ad.
#: Kullanıcının elindeki config'in yeniden adlandırma yüzünden patlaması,
#: davranışın korunduğu bir taşımada kabul edilebilir değil.
RENAMED_KEYS = {
    "runtime": {"agent_max_iterations": "agent_max_steps"},
}

#: Taşınmayan ayarlar: neden yok olduklarını söyleyebilmek için. Sessizce
#: yutulmazlar — kullanıcı bir şey ayarladığını sanıp beklentiye girmesin.
REMOVED_KEYS = {
    "runtime": {
        "live_input": "tur sürerken canlı giriş henüz taşınmadı",
        "hedge_delay_s": (
            "yedek zinciri artık yarıştırılmıyor, SIRALI deneniyor — öncelik "
            "penceresinin karşılığı kalmadı. Geçici arıza `retry_delays_s` ile "
            "AYNI modelde karşılanıyor"
        ),
    },
}


def _apply_renames(data: YamlMapping) -> YamlMapping:
    """Eski adla yazılmış ayarları yeni adlarına taşı."""
    result = dict(data)
    for section, renames in RENAMED_KEYS.items():
        raw = result.get(section)
        if not isinstance(raw, dict):
            continue
        section_data = dict(raw)
        for old, new in renames.items():
            if old in section_data:
                # Yeni ad da yazılmışsa kullanıcının açık tercihi odur.
                section_data.setdefault(new, section_data[old])
                del section_data[old]
        result[section] = section_data
    return result


def _reject_removed(data: YamlMapping) -> None:
    """Taşınmamış ayarlar için genel liste yerine sebebini söyleyen hata ver."""
    for section, removed in REMOVED_KEYS.items():
        raw = data.get(section)
        if not isinstance(raw, dict):
            continue
        for key, reason in removed.items():
            if key in raw:
                raise ConfigError(f"{section}.{key}: bu ayar artık yok — {reason}. Satırı sil.")


def _first_existing(candidates: tuple[Path, ...]) -> Path | None:
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _deep_merge(base: YamlMapping, overlay: YamlMapping) -> YamlMapping:
    """`overlay`'i `base` üzerine derin birleştir. Liste değerleri değiştirilir, eklenmez."""
    merged: YamlMapping = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


# --------------------------------------------------------------------------- #
# Doğrulama ve dönüştürme
# --------------------------------------------------------------------------- #


def _reject_unknown(data: YamlMapping, allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ConfigError(
            f"{where}: bilinmeyen anahtar {', '.join(unknown)}. "
            f"Beklenenler: {', '.join(sorted(allowed))}"
            "\nYalnızca DEĞİŞTİRMEK istediğin anahtarları yaz; gerisi zaten varsayılan."
        )


def _build(cls: type[T], data: object, where: str) -> T:
    """Bir sözlüğü dataclass'a dönüştür; eksik/fazla/yanlış tipli alanı hata yap."""
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: sözlük bekleniyordu, gelen: {type(data).__name__}")

    hints = get_type_hints(cls)
    fields = {field.name: field for field in dataclasses.fields(cls)}  # type: ignore[arg-type]
    _reject_unknown(data, tuple(fields), where)

    values: dict[str, object] = {}
    for name, field in fields.items():
        if name in data:
            values[name] = _convert(data[name], hints[name], f"{where}.{name}")
        elif _has_default(field):
            continue
        else:
            raise ConfigError(
                f"{where}: '{name}' alanı eksik. Varsayılanı `defaults.yaml` içinde tanımlı olmalı."
            )
    return cls(**values)


def _has_default(field: dataclasses.Field[Any]) -> bool:
    return (
        field.default is not dataclasses.MISSING or field.default_factory is not dataclasses.MISSING
    )


def _convert(value: object, target: object, where: str) -> object:
    """Ham YAML değerini hedef tipe çevir; uymuyorsa anlaşılır hata ver."""
    optional = _optional_inner(target)
    if optional is not None:
        # `X | None`: YAML'da yazılmamış ya da açıkça `null` yazılmış alan None kalır,
        # dolu alan `X` gibi çevrilir. Bu genel kural, tek bir alan için özel dal
        # açmaya gerek bırakmaz.
        return None if value is None else _convert(value, optional, where)

    if dataclasses.is_dataclass(target) and isinstance(target, type):
        return _build(target, value, where)

    if get_origin(target) is Literal:
        if any(type(value) is type(option) and value == option for option in get_args(target)):
            return value
        raise ConfigError(f"{where}: izin verilen değerlerden biri gerekli.")
    if get_origin(target) is tuple:
        return _convert_tuple(value, target, where)
    if get_origin(target) is dict:
        return _convert_dict(value, target, where)

    if target is bool:
        return _expect(value, bool, "boolean", where)
    if target is int:
        # `bool` Python'da `int` alt tipidir; ayarlarda sayı beklenen yere True sızmasın.
        if isinstance(value, bool):
            raise ConfigError(f"{where}: tam sayı bekleniyordu, gelen: boolean")
        return _expect(value, int, "tam sayı", where)
    if target is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where}: sayı bekleniyordu, gelen: {type(value).__name__}")
        return float(value)
    if target is str:
        return _expect(value, str, "metin", where)
    if isinstance(target, type) and issubclass(target, Enum):
        return _convert_enum(value, target, where)

    raise ConfigError(f"{where}: desteklenmeyen ayar tipi: {target!r}")


def _convert_enum(value: object, target: type[Enum], where: str) -> Enum:
    """YAML değerini bir Enum üyesine çevir; geçersizse izin verilenleri say."""
    try:
        return target(value)
    except ValueError:
        allowed = ", ".join(str(member.value) for member in target)
        raise ConfigError(f"{where}: geçersiz değer '{value}'. İzin verilen: {allowed}") from None


def _optional_inner(target: object) -> object | None:
    """Hedef `X | None` ise `X`'i, değilse None döndür.

    İki union sözdizimi de tanınır: `X | None` (`types.UnionType`) ve
    `Optional[X]` (`typing.Union`). Yalnızca TEK gerçek tip + None desteklenir;
    çok üyeli union'da hangi üyeye çevrileceği belirsiz olurdu ve sessizce
    yanlış tipe düşmek yapılandırma katmanında kabul edilemez.
    """
    if get_origin(target) not in (UnionType, Union):
        return None
    members = [arg for arg in get_args(target) if arg is not type(None)]
    return members[0] if len(members) == 1 else None


def _convert_dict(value: object, target: object, where: str) -> dict[str, object]:
    """`dict[str, X]`: anahtarlar metin, değerler `X` tipine çevrilir."""
    (key_type, item_type) = get_args(target)
    if key_type is not str:
        raise ConfigError(f"{where}: yalnız metin anahtarlı sözlük desteklenir")
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: sözlük bekleniyordu, gelen: {type(value).__name__}")
    return {str(key): _convert(item, item_type, f"{where}.{key}") for key, item in value.items()}


def _convert_tuple(value: object, target: object, where: str) -> tuple[object, ...]:
    (item_type, *_) = get_args(target)
    if where == "runtime.lsp_server.command" and isinstance(value, str):
        raise ConfigError(f"{where}: açık argv listesi gerekli; metin komut kabul edilmez.")
    # Metin listesi beklenen yere yazılan TEK metin, tek elemanlı liste sayılır.
    # Önceki sürüm `fallback: str | list[str]` kabul ediyordu; kullanıcıların
    # elindeki `fallback: bir/model` yazan config'ler yükleme anında patlamasın.
    # Belirsizlik yok: metin listesinde tek metnin başka anlamı olamaz.
    if item_type is str and isinstance(value, str):
        return (value,)
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ConfigError(f"{where}: liste bekleniyordu, gelen: {type(value).__name__}")
    return tuple(_convert(item, item_type, f"{where}[{index}]") for index, item in enumerate(value))


def _expect(value: object, target: type[T], label: str, where: str) -> T:
    if not isinstance(value, target):
        raise ConfigError(f"{where}: {label} bekleniyordu, gelen: {type(value).__name__}")
    return value
