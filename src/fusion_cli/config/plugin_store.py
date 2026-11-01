"""Kurulu eklentilerin kaydı ve etkin eklentilerin bileşenleri (P-059).

Yerleşim: `<veri>/eklentiler/<ad>/` (eklentinin kopyası) ve `<veri>/eklentiler/kayit.json`:

    {"surum": 1, "hepsi_kapali": false,
     "eklentiler": {"<ad>": {"surum", "kaynak", "tur", "pazar", "commit", "karma",
                            "etkin", "calistirma_onayi", "kurulum"}},
     "pazarlar": {"<ad>": {"kaynak", "tur", "yol", "eklendi"}}}

Güven sözleşmesi:
- Kurulumda içerik karması (`tree_digest`) kaydedilir. Yüklemede yeniden hesaplanır; dosyalar
  kurulumdan sonra değiştiyse eklentinin HİÇBİR bileşeni yüklenmez ("değişmiş") — yeniden
  onay `fusion eklenti guven <ad>` ya da yeniden kurulum ister.
- Kanca ve MCP (Fusion dışında süreç başlatan bileşenler) yalnız kurulumda açıkça onaylandıysa
  (`calistirma_onayi`) yüklenir; MCP kayıtları `unreviewed` güvenle girer.
- Kapatma: eklenti başına `etkin: false`, hepsi için `hepsi_kapali: true`
  (`fusion eklenti kapat --hepsi`) ya da `FUSION_PLUGINS=off` ortam değişkeni.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugins import NAME_PATTERN, PluginError
from .models import McpServerConfig
from .paths import user_data_dir
from .plugin_layout import PluginLayout, hook_blocks, mcp_servers, scan_plugin, tree_digest

_LOG = logging.getLogger(__name__)

PLUGINS_DIRNAME = "eklentiler"
STATE_NAME = "kayit.json"
STATE_VERSION = 1
#: Bütün eklentileri kapatan ortam değişkeni ve kapalı sayılan değerler.
PLUGINS_ENV = "FUSION_PLUGINS"
_OFF_VALUES = frozenset({"0", "off", "false", "no", "kapali", "kapalı"})

#: Eklenti kancaları çalıştırılıyor mu? Kanca yükleyicisi (`config/hooks.py` →
#: `config/plugin_hooks.py`) `plugin_hook_blocks()`'u tüketir (#375). Ad, önizleme/liste
#: yüzeylerinin geri uyumu için korunur.
PLUGIN_HOOKS_ACTIVE = True

#: Kayıt durumları (kullanıcıya bu adlarla görünür).
STATUS_ACTIVE = "etkin"
STATUS_DISABLED = "kapalı"
STATUS_TAMPERED = "değişmiş"
STATUS_BROKEN = "bozuk"


@dataclass(frozen=True, slots=True)
class PluginRecord:
    name: str
    version: str = ""
    source: str = ""
    #: `yerel` | `git` | `pazar`
    kind: str = "yerel"
    marketplace: str = ""
    commit: str = ""
    digest: str = ""
    enabled: bool = True
    #: Kanca/MCP çalıştırma onayı kurulumda verildi mi?
    exec_approved: bool = False
    installed_at: float = 0.0


@dataclass(frozen=True, slots=True)
class MarketplaceRecord:
    name: str
    source: str
    #: `yerel` | `git`
    kind: str
    #: Pazarın diskteki kökü (yerel klasör ya da klon).
    path: str
    added_at: float = 0.0


@dataclass(frozen=True, slots=True)
class PluginState:
    plugins: tuple[PluginRecord, ...] = ()
    marketplaces: tuple[MarketplaceRecord, ...] = ()
    all_disabled: bool = False

    def plugin(self, name: str) -> PluginRecord | None:
        return next((item for item in self.plugins if item.name == name), None)

    def marketplace(self, name: str) -> MarketplaceRecord | None:
        return next((item for item in self.marketplaces if item.name == name), None)

    def with_plugin(self, record: PluginRecord) -> PluginState:
        others = tuple(item for item in self.plugins if item.name != record.name)
        return replace(self, plugins=(*others, record))

    def without_plugin(self, name: str) -> PluginState:
        return replace(self, plugins=tuple(i for i in self.plugins if i.name != name))

    def with_marketplace(self, record: MarketplaceRecord) -> PluginState:
        others = tuple(item for item in self.marketplaces if item.name != record.name)
        return replace(self, marketplaces=(*others, record))

    def without_marketplace(self, name: str) -> PluginState:
        return replace(self, marketplaces=tuple(i for i in self.marketplaces if i.name != name))


@dataclass(frozen=True, slots=True)
class InstalledPlugin:
    """Kayıt + diskteki düzen + bütünlük durumu."""

    record: PluginRecord
    layout: PluginLayout | None
    status: str
    detail: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE and self.layout is not None


def plugins_dir() -> Path:
    return user_data_dir() / PLUGINS_DIRNAME


def state_file(base: Path | None = None) -> Path:
    return (base or plugins_dir()) / STATE_NAME


def plugins_disabled_by_environment() -> bool:
    return os.environ.get(PLUGINS_ENV, "").strip().lower() in _OFF_VALUES


def load_state(base: Path | None = None) -> PluginState:
    """Kaydı oku; yoksa boş. Bozuk dosya eklenti AÇMAZ (boş + günlük uyarısı)."""
    path = state_file(base)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return PluginState()
    except (OSError, ValueError) as error:
        _LOG.warning("eklenti kaydı okunamadı (%s): %s", path, error)
        return PluginState()
    if not isinstance(raw, Mapping):
        return PluginState()
    return PluginState(
        # Elle bozulmuş kayıttaki `../x` gibi ad klasör yoluna dönüşmesin: geçersiz ad atlanır.
        tuple(
            _plugin(name, item)
            for name, item in _items(raw.get("eklentiler"))
            if NAME_PATTERN.match(name)
        ),
        tuple(
            _marketplace(name, item)
            for name, item in _items(raw.get("pazarlar"))
            if NAME_PATTERN.match(name)
        ),
        raw.get("hepsi_kapali") is True,
    )


def _items(raw: object) -> tuple[tuple[str, Mapping[str, object]], ...]:
    if not isinstance(raw, Mapping):
        return ()
    return tuple((str(k), v) for k, v in raw.items() if isinstance(v, Mapping))


def _plugin(name: str, raw: Mapping[str, object]) -> PluginRecord:
    return PluginRecord(
        name=name,
        version=str(raw.get("surum") or ""),
        source=str(raw.get("kaynak") or ""),
        kind=str(raw.get("tur") or "yerel"),
        marketplace=str(raw.get("pazar") or ""),
        commit=str(raw.get("commit") or ""),
        digest=str(raw.get("karma") or ""),
        enabled=raw.get("etkin") is not False,
        exec_approved=raw.get("calistirma_onayi") is True,
        installed_at=_number(raw.get("kurulum")),
    )


def _marketplace(name: str, raw: Mapping[str, object]) -> MarketplaceRecord:
    return MarketplaceRecord(
        name,
        str(raw.get("kaynak") or ""),
        str(raw.get("tur") or "yerel"),
        str(raw.get("yol") or ""),
        _number(raw.get("eklendi")),
    )


def _number(raw: object) -> float:
    return float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else 0.0


def save_state(state: PluginState, base: Path | None = None) -> Path:
    path = state_file(base)
    payload = {
        "surum": STATE_VERSION,
        "hepsi_kapali": state.all_disabled,
        "eklentiler": {
            p.name: {
                "surum": p.version,
                "kaynak": p.source,
                "tur": p.kind,
                "pazar": p.marketplace,
                "commit": p.commit,
                "karma": p.digest,
                "etkin": p.enabled,
                "calistirma_onayi": p.exec_approved,
                "kurulum": p.installed_at,
            }
            for p in sorted(state.plugins, key=lambda item: item.name)
        },
        "pazarlar": {
            m.name: {"kaynak": m.source, "tur": m.kind, "yol": m.path, "eklendi": m.added_at}
            for m in sorted(state.marketplaces, key=lambda item: item.name)
        },
    }
    atomic_replace_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def update_state(
    change: Callable[[PluginState], PluginState], base: Path | None = None
) -> PluginState:
    """Kaydı süreçler arası kilit altında oku-değiştir-yaz.

    Ölçüldü (31 Ekim): masaüstü ve CLI aynı anda kur/aç/kapat yaptığında `kayit.json` son
    yazanın değerine düşüyordu (kimlik deposu `config_lock` kullanıyor, burada kilit yoktu).
    """
    from .writer import config_lock

    path = state_file(base)
    with config_lock(path):
        updated = change(load_state(base))
        save_state(updated, base)
    return updated


def inspect_plugin(record: PluginRecord, base: Path | None = None) -> InstalledPlugin:
    """Kaydı diskle karşılaştır: etkin / kapalı / değişmiş / bozuk."""
    folder = (base or plugins_dir()) / record.name
    try:
        layout = scan_plugin(folder)
        digest = tree_digest(folder)
    except (PluginError, OSError) as error:
        return InstalledPlugin(record, None, STATUS_BROKEN, str(error))
    if record.digest and digest != record.digest:
        return InstalledPlugin(record, layout, STATUS_TAMPERED, "dosyalar kurulumdan sonra değişti")
    return InstalledPlugin(record, layout, STATUS_ACTIVE if record.enabled else STATUS_DISABLED)


def plugin_id(record: PluginRecord) -> str:
    """Claude kimliği `ad@pazar`; pazarsız (yerel/git) kurulumda yalnız ad (#376)."""
    return f"{record.name}@{record.marketplace}" if record.marketplace else record.name


def effective_record(record: PluginRecord, root: Path | None = None) -> PluginRecord:
    """`enabledPlugins` project/local katmanları uygulanmış kayıt (#376)."""
    from .plugin_scopes import resolve_enabled

    project = root or Path.cwd()
    decision = resolve_enabled(plugin_id(record), record.name, record.enabled, project)
    if decision.enabled == record.enabled:
        return record
    return replace(record, enabled=decision.enabled)


def installed_plugins(
    base: Path | None = None, root: Path | None = None
) -> tuple[InstalledPlugin, ...]:
    state = load_state(base)
    return tuple(
        inspect_plugin(effective_record(record, root), base)
        for record in sorted(state.plugins, key=_by_name)
    )


def _by_name(record: PluginRecord) -> str:
    return record.name


def active_plugins(
    base: Path | None = None, root: Path | None = None
) -> tuple[InstalledPlugin, ...]:
    """Bileşenleri yüklenecek eklentiler (genel kapatma, kapsamlar ve bütünlük denetimi sonrası)."""
    if plugins_disabled_by_environment():
        return ()
    state = load_state(base)
    if state.all_disabled:
        return ()
    records = (effective_record(r, root) for r in sorted(state.plugins, key=_by_name))
    found = (inspect_plugin(r, base) for r in records if r.enabled)
    active: list[InstalledPlugin] = []
    for item in found:
        if item.is_active:
            active.append(item)
        elif item.status != STATUS_DISABLED:
            _LOG.warning(
                "eklenti '%s' yüklenmedi: %s %s", item.record.name, item.status, item.detail
            )
    return tuple(active)


def plugin_mcp_servers(base: Path | None = None) -> tuple[McpServerConfig, ...]:
    """Etkin ve çalıştırma onaylı eklentilerin MCP sunucuları.

    Ölçüldü (31 Ekim): ad slug'ı (`plugin_<eklenti>_<sunucu>`) iki eklentide çakışabiliyordu
    (`foo`/`bar-baz` ile `foo-bar`/`baz`); ikisi de yükleniyor, araç adları birbirini eziyordu.
    Ada göre ilk eklenti kazanır, sonraki atlanır ve günlüğe yazılır.
    """
    servers: list[McpServerConfig] = []
    owners: dict[str, str] = {}
    for item in active_plugins(base):
        if item.layout is None or not item.record.exec_approved:
            continue
        try:
            found = mcp_servers(item.layout)
        except PluginError as error:
            _LOG.warning("eklenti '%s' MCP tanımı yüklenmedi: %s", item.record.name, error)
            continue
        for server in found:
            owner = owners.setdefault(server.name, item.record.name)
            if owner != item.record.name:
                _LOG.warning(
                    "eklenti '%s' MCP sunucusu '%s' atlandı: '%s' eklentisiyle ad çakışması",
                    item.record.name,
                    server.name,
                    owner,
                )
                continue
            servers.append(server)
    return tuple(servers)


def plugin_hook_blocks(
    base: Path | None = None,
) -> tuple[tuple[str, Path, Mapping[str, object]], ...]:
    """`(kaynak adı, dosya, {"hooks": …})`: kanca yükleyicisinin (P-009) okuyacağı katmanlar.

    Kaynak adı `eklenti:<ad>`; yalnız çalıştırma onaylı etkin eklentiler.
    """
    blocks: list[tuple[str, Path, Mapping[str, object]]] = []
    for item in active_plugins(base):
        if item.layout is None or not item.record.exec_approved:
            continue
        try:
            blocks.extend(
                (f"eklenti:{item.record.name}", p, b) for p, b in hook_blocks(item.layout)
            )
        except PluginError as error:
            _LOG.warning("eklenti '%s' kancaları yüklenmedi: %s", item.record.name, error)
    return tuple(blocks)


def plugin_root_of(path: Path, base: Path | None = None) -> Path | None:
    """`path` kurulu bir eklentinin içindeyse o eklentinin kökü (geçici/pazar klasörü değil)."""
    try:
        root = (base or plugins_dir()).resolve()
        relative = path.resolve().relative_to(root)
    except (OSError, ValueError):
        return None
    first = relative.parts[0] if len(relative.parts) > 1 else ""
    return root / first if first and not first.startswith(".") else None


def state_signature(base: Path | None = None, root: Path | None = None) -> tuple[str, int] | None:
    """Kayıt dosyasının (yol, mtime_ns) imzası: kur/kapat/kaldır katalog önbelleğini yeniler.

    project/local `enabledPlugins` dosyalarının mtime'ları da karışır (#376).
    """
    from .plugin_scopes import settings_signature

    path = state_file(base)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    return str(path), hash((mtime, *settings_signature(root or Path.cwd())))
