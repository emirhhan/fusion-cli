"""İzin kurallarını yönetme (P-003): `/permissions`, `fusion permissions` ve `izin.*` RPC'leri
aynı üç işlevi çağırır — tek doğruluk kaynağı, üç giriş noktası (RULES.md "UI ve CLI").

Hedef dosya seçimi Claude Code'la aynıdır: kural varsayılan olarak projenin
`.claude/settings.local.json`'ına yazılır (güvenilen projede ya da izin dosyası henüz
yokken; Fusion'ın yazdığı dosyanın karması güven kaydına işlenir), `--user` ile ya da
proje izin dosyası güvenilmiyorken kullanıcının `permissions.json`'ına.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ..core.errors import ConfigError
from ..ui import messages
from . import trust
from .local_settings_gitignore import ensure_globally_ignored
from .local_settings_location import local_settings_path, local_settings_root
from .models import Config
from .permission_rules import (
    LAYER_FUSION,
    LAYER_LOCAL,
    LAYER_PROJECT,
    LAYER_USER,
    PermissionDecision,
    PermissionRule,
    RuleRow,
    add_rule,
    format_rule,
    list_rule_rows,
    load_permission_rules,
    parse_rule,
    read_rules_file,
    remove_rule,
    rule_layers,
    user_rule_file,
)
from .writer import write_runtime_flag

#: Ayarlar › İzinler'deki iki kök-dışı engel anahtarı (`runtime.*`).
OUTSIDE_ROOT_FLAGS = ("block_reads_outside_root", "block_writes_outside_root")


def project_rule_file(root: Path) -> Path:
    """Varsayılan hedef: güvenilen (ya da izin dosyasız) projede yerel ayar, yoksa kullanıcı."""
    if trust.is_permissions_trusted(root):
        return local_settings_path(root)
    return user_rule_file()


def parse_decision(raw: object) -> PermissionDecision:
    """`allow|ask|deny` metnini karara çevir; bilinmiyorsa `ValueError`."""
    text = str(raw or "").strip().lower()
    try:
        return PermissionDecision(text)
    except ValueError as error:
        raise ValueError(text) from error


def parse_pattern(raw: object, decision: PermissionDecision) -> PermissionRule:
    """`Araç(belirteç)` metnini kurala çevir; bozuksa `ValueError`."""
    rule = parse_rule(raw, decision)
    if rule is None:
        raise ValueError(str(raw))
    return rule


@dataclass(frozen=True, slots=True)
class RuleChange:
    """Ekleme/silme sonucu: kural, yazılan dosya ve gerçekten değişip değişmediği."""

    rule: PermissionRule
    path: Path
    changed: bool
    #: Proje istenmişti ama izin dosyası güvenilmediği için kullanıcı dosyasına düşüldü
    #: (kapsam: TÜM projeler). Çağıran bunu kullanıcıya açıkça söyler.
    fell_back: bool = False

    @property
    def pattern(self) -> str:
        return format_rule(self.rule)


def add_permission_rule(
    root: Path, rule: PermissionRule, *, user_level: bool = False, strict_project: bool = False
) -> RuleChange:
    """Kuralı hedef dosyaya ekle; proje dosyasına yazıldıysa güven karmasını tazele.

    Proje izin dosyası güvenilmiyorsa hedef kullanıcı dosyasına düşer ve `fell_back` işaretlenir
    (ölçüldü, 31 Ekim: masaüstünde "Bu proje" seçilirken kural sessizce tüm projelere
    yazılıyordu). `strict_project` ile bu düşüş `ConfigError` olur (masaüstü "Bu proje" kapsamı).
    """
    project_target = local_settings_path(root)
    target = user_rule_file() if user_level else project_rule_file(root)
    fell_back = not user_level and target != project_target
    if fell_back and strict_project:
        raise ConfigError(messages.PERMISSIONS_PROJECT_UNTRUSTED)
    created = target == project_target and not target.exists()
    changed = add_rule(target, rule)
    if changed and target == project_target:
        trust.record_permissions_digest(root)
    if created and target.is_file():
        # Claude (#67): ilk yazımda dosya genel git dışlamasına eklenir.
        ensure_globally_ignored(local_settings_root(root))
    return RuleChange(rule, target, changed, fell_back)


#: Fusion'ın YAZDIĞI katmanlar; ötekiler (`~/.claude/settings.json`, proje `settings.json`)
#: Claude Code'un dosyalarıdır ve yalnız okunur (tasarım kararı 3).
WRITABLE_LAYERS = frozenset({LAYER_FUSION, LAYER_USER, LAYER_LOCAL})


def is_rule_removable(root: Path, layer_name: str) -> bool:
    """Bu katmandaki bir satır Fusion'dan silinebilir mi? (RPC/arayüz `silinebilir`.)

    Yazılabilir katman olmalı; yerel dosya ayrıca GÜVENİLİR olmalı (güvenilmeyen
    dosyadan silmek karmayı tazeler ve kalan `Bash(*)`ı aktif ederdi).
    """
    if layer_name not in WRITABLE_LAYERS:
        return False
    return layer_name != LAYER_LOCAL or trust.is_permissions_trusted(root)


def added_message(change: RuleChange, decision: PermissionDecision) -> str:
    """Ekleme sonucunun metni; kullanıcı dosyasına düşüldüyse kapsamı (TÜM PROJELER) söyler."""
    template = (
        messages.PERMISSIONS_ADDED_FALLBACK if change.fell_back else messages.PERMISSIONS_ADDED
    )
    return template.format(rule=change.pattern, decision=decision.value, path=change.path)


def remove_permission_rule(
    root: Path, rule: PermissionRule, *, path: Path | None = None
) -> RuleChange | None:
    """Kuralı taşıyan ilk YAZILABİLİR katmandan (ya da `path` verilmişse o dosyadan) sil.

    Hiçbir katmanda yoksa `None`. Salt okunur katmandan (Claude'un dosyaları) ya da
    güvenilmeyen yerel dosyadan silme `ConfigError` ile REDDEDİLİR. Ölçüldü (31 Ekim):
    güven kontrolü silmeden sonra ve `config.yaml` güvenine bakıyordu; güvenilmeyen
    dosyadan masum bir satır silinince karma tazeleniyor ve dosyadaki `Bash(*)` allow
    aktif oluyordu. Tersi de vardı: Fusion'ın yazdığı (sentinel kayıtlı) dosyadan silince
    karma tazelenmiyor, kalan deny kuralları da düşüyordu. Artık yerel dosyadan silmenin
    tek koşulu dosyanın SİLMEDEN ÖNCE güvenilir olmasıdır; silindikten sonra karma
    koşulsuz tazelenir.
    """
    layers = [layer for layer in rule_layers(root) if path is None or layer.path == path]
    if path is not None and not layers:
        raise ConfigError(f"İzin dosyası bilinen bir katman değil: {path}")
    for layer in layers:
        if not _holds_rule(layer.path, rule):
            continue
        if layer.name not in WRITABLE_LAYERS:
            raise ConfigError(
                f"{layer.description} salt okunur ({layer.path}); kuralı o dosyadan elle kaldır."
            )
        trusted_before = layer.name != LAYER_LOCAL or trust.is_permissions_trusted(root)
        if not trusted_before:
            raise ConfigError(
                f"Proje yerel izin dosyası güvenilmiyor ({layer.path}); silmek izin açmaz. "
                "Önce `fusion trust` ile dosyayı güvenilir yap ya da elle düzenle."
            )
        if not remove_rule(layer.path, rule):
            continue
        if layer.name == LAYER_LOCAL:
            trust.record_permissions_digest(root)
        return RuleChange(rule, layer.path, True)
    return None


def _holds_rule(path: Path, rule: PermissionRule) -> bool:
    return any(found == rule_without_source(rule) for found in read_rules_file(path))


def rule_without_source(rule: PermissionRule) -> PermissionRule:
    return PermissionRule(rule.tool, rule.specifier, rule.decision)


def rule_rows(root: Path) -> tuple[RuleRow, ...]:
    return list_rule_rows(root)


def rules_payload(root: Path, config: Config) -> dict[str, object]:
    """RPC/arayüz için tam tablo: kurallar, güvensiz katmanlar, hedef dosya, engeller."""
    loaded = load_permission_rules(
        root,
        block_reads_outside_root=config.runtime.block_reads_outside_root,
        block_writes_outside_root=config.runtime.block_writes_outside_root,
    )
    return {
        "ok": True,
        "kurallar": [
            {
                "kalip": row.pattern,
                "karar": row.decision,
                "kaynak": row.source,
                "dosya": row.path,
                "silinebilir": is_rule_removable(root, row.source.split(" ", 1)[0]),
            }
            for row in list_rule_rows(root)
        ],
        "guvensiz_katmanlar": list(loaded.untrusted_layers),
        "hedef": str(project_rule_file(root)),
        "kullanici_dosyasi": str(user_rule_file()),
        "katmanlar": [
            {"ad": layer.name, "dosya": str(layer.path), "aciklama": layer.description}
            for layer in rule_layers(root)
        ],
        "kok_disi_okuma_engeli": config.runtime.block_reads_outside_root,
        "kok_disi_yazma_engeli": config.runtime.block_writes_outside_root,
        "proje_katmani_guvenli": LAYER_PROJECT not in loaded.untrusted_layers,
    }


def set_outside_root_flag(config: Config, key: str, value: bool) -> Config:
    """Kök-dışı engel anahtarını kalıcı yaz ve güncel yapılandırmayı döndür."""
    if key not in OUTSIDE_ROOT_FLAGS:
        raise ValueError(f"Bilinmeyen engel anahtarı: {key}")
    try:
        write_runtime_flag(config, key, bool(value))
    except OSError as error:
        raise ConfigError(f"Engel anahtarı yazılamadı ({key}): {error}") from error
    runtime = (
        replace(config.runtime, block_reads_outside_root=bool(value))
        if key == "block_reads_outside_root"
        else replace(config.runtime, block_writes_outside_root=bool(value))
    )
    return replace(config, runtime=runtime)
