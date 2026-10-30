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
from . import trust
from .models import Config
from .permission_rules import (
    LAYER_LOCAL,
    LAYER_PROJECT,
    PermissionDecision,
    PermissionRule,
    RuleRow,
    add_rule,
    format_rule,
    list_rule_rows,
    load_permission_rules,
    parse_rule,
    remove_rule,
    rule_layers,
    user_permissions_file,
)
from .writer import write_runtime_flag

#: Ayarlar › İzinler'deki iki kök-dışı engel anahtarı (`runtime.*`).
OUTSIDE_ROOT_FLAGS = ("block_reads_outside_root", "block_writes_outside_root")


def project_rule_file(root: Path) -> Path:
    """Varsayılan hedef: güvenilen (ya da izin dosyasız) projede yerel ayar, yoksa kullanıcı."""
    if trust.is_permissions_trusted(root):
        return root / trust.PROJECT_PERMISSIONS_PATH
    return user_permissions_file()


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

    @property
    def pattern(self) -> str:
        return format_rule(self.rule)


def add_permission_rule(
    root: Path, rule: PermissionRule, *, user_level: bool = False
) -> RuleChange:
    """Kuralı hedef dosyaya ekle; proje dosyasına yazıldıysa güven karmasını tazele."""
    target = user_permissions_file() if user_level else project_rule_file(root)
    changed = add_rule(target, rule)
    if changed and target == root / trust.PROJECT_PERMISSIONS_PATH:
        trust.record_permissions_digest(root)
    return RuleChange(rule, target, changed)


def remove_permission_rule(root: Path, rule: PermissionRule) -> RuleChange | None:
    """Kuralı taşıyan İLK katmandan sil; hiçbir katmanda yoksa `None`.

    Proje dosyasından silmek, dosya güveniliyorsa karmayı tazeler; güvenilmiyorsa
    dosya güvensiz kalmaya devam eder (silmek izin AÇMAZ).
    """
    for layer in rule_layers(root):
        if not remove_rule(layer.path, rule):
            continue
        if layer.name == LAYER_LOCAL and trust.resolve_project_trust(root).trusted:
            trust.record_permissions_digest(root)
        return RuleChange(rule, layer.path, True)
    return None


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
            {"kalip": row.pattern, "karar": row.decision, "kaynak": row.source, "dosya": row.path}
            for row in list_rule_rows(root)
        ],
        "guvensiz_katmanlar": list(loaded.untrusted_layers),
        "hedef": str(project_rule_file(root)),
        "kullanici_dosyasi": str(user_permissions_file()),
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
