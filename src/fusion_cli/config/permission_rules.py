"""İzin kuralı grameri ve ayar katmanları (P-001) — Claude Code ile aynı dosya biçimi.

Bir kural `Araç` ya da `Araç(belirteç)` biçimindedir ve üç listeden birinde durur:

    permissions.allow   sorulmadan çalışır
    permissions.ask     kip ne olursa olsun sorulur
    permissions.deny    hiçbir kipte çalışmaz ("İzinleri atla" dahil)

Araç adı Claude'un adı (`Bash`, `Read`, `Edit`, `Write`, `WebFetch`, `WebSearch`,
`Skill`, `Agent`, `mcp__sunucu__araç`) ya da doğrudan bir Fusion aracı (`desktop_click`)
olabilir. Belirteç aracın türüne göre yorumlanır (bkz. `tools/permission_match.py`):
kabukta ön ek (`npm run *`), dosyada glob (`/src/**`, `~/x/**`, `//etc/*`), web'de
`domain:…`, ötekilerde ad ön eki.

Katmanlar (hepsi aynı JSON şemasıyla): Fusion'ın kullanıcı dosyası, Claude'un
`~/.claude/settings.json`'ı, projenin `.claude/settings.json`'ı ve `.claude/settings.local.json`'ı.
Proje içi iki dosya YALNIZ `fusion trust` sonrası ve içerik o günden beri değişmediyse
okunur: indirilmiş bir depo `Bash(*)` taşıyabilir (bkz. `trust.py`).

Birleşim sırası önemsizdir: eşleşen kurallar arasında EN KISITLAYICI kazanır
(deny → ask → allow); Codex `.rules` ve Claude'un deny önceliği aynı ilkeyi uygular.
Bu modül `core` dışında hiçbir katmana bağlı değildir; eşleme `tools` katmanındadır.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..core.errors import ConfigError
from .paths import user_config_dir
from .trust import (
    PROJECT_PERMISSIONS_PATH,
    PROJECT_SETTINGS_PATH,
    is_permissions_trusted,
    is_project_settings_trusted,
)

#: Fusion'ın kendi kalıcı izin dosyası (kullanıcıya ait; proje dışı).
USER_PERMISSIONS_NAME = "permissions.json"
#: Claude Code'un kullanıcı düzeyi ayar dosyası.
CLAUDE_USER_SETTINGS = Path(".claude") / "settings.json"

#: Katman adları — RPC ve arayüzde "kaynak" olarak gösterilir.
LAYER_FUSION = "fusion"
LAYER_USER = "kullanici"
LAYER_PROJECT = "proje"
LAYER_LOCAL = "yerel"


class PermissionDecision(Enum):
    """Bir kuralın kararı; değer JSON'daki liste adıdır."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


#: Kısıtlayıcılık sırası: küçük sayı daha kısıtlayıcı.
_STRICTNESS = {PermissionDecision.DENY: 0, PermissionDecision.ASK: 1, PermissionDecision.ALLOW: 2}


def stricter(first: PermissionDecision, second: PermissionDecision) -> PermissionDecision:
    """İki karardan daha kısıtlayıcı olanı."""
    return first if _STRICTNESS[first] <= _STRICTNESS[second] else second


@dataclass(frozen=True, slots=True)
class PermissionRule:
    """Tek bir izin kuralı."""

    tool: str
    specifier: str | None
    decision: PermissionDecision
    #: Hangi katmandan geldiği (`LAYER_*`); elle kurulan kuralda serbest metin.
    source: str = ""

    @property
    def pattern(self) -> str:
        """Dosyadaki yazımı: `Araç(belirteç)` ya da `Araç`."""
        return format_rule(self)


def parse_rule(
    entry: object, decision: PermissionDecision, *, source: str = ""
) -> PermissionRule | None:
    """`Bash(npm run *)` metnini kurala çevir; bozuk yazım `None` (yok sayılır)."""
    if not isinstance(entry, str):
        return None
    text = entry.strip()
    if not text:
        return None
    if text.endswith(")"):
        if "(" not in text:
            return None
        head, _, body = text[:-1].partition("(")
        if not head.strip() or "(" in body:
            return None
        return PermissionRule(head.strip(), body.strip() or None, decision, source)
    if "(" in text or ")" in text:
        return None
    return PermissionRule(text, None, decision, source)


def format_rule(rule: PermissionRule) -> str:
    return f"{rule.tool}({rule.specifier})" if rule.specifier else rule.tool


@dataclass(frozen=True, slots=True)
class PermissionRuleSet:
    """Tüm katmanlardan okunmuş kurallar ve kök-dışı engel anahtarları (P-002)."""

    rules: tuple[PermissionRule, ...] = ()
    #: Açıkken dosya araçları proje kökü (+ `--add-dir`) DIŞINI okuyamaz.
    block_reads_outside_root: bool = False
    #: Açıkken dosya araçları proje kökü (+ `--add-dir`) DIŞINA yazamaz; onay da sorulmaz.
    block_writes_outside_root: bool = False
    #: Dosyası var ama güvenilmediği için atlanan katmanlar.
    untrusted_layers: tuple[str, ...] = ()

    def with_rules(self, rules: Iterable[PermissionRule]) -> PermissionRuleSet:
        return PermissionRuleSet(
            tuple(rules),
            self.block_reads_outside_root,
            self.block_writes_outside_root,
            self.untrusted_layers,
        )


@dataclass(frozen=True, slots=True)
class RuleLayer:
    """Bir izin dosyası ve güven koşulu."""

    name: str
    path: Path
    #: Okunması için projeye güvenilmesi gerekir mi?
    requires_trust: bool = False
    #: Kullanıcı arayüzünde gösterilen açıklama.
    description: str = ""


def rule_layers(root: Path) -> tuple[RuleLayer, ...]:
    """Okuma sırasıyla katmanlar: fusion → kullanıcı → proje → yerel."""
    return (
        RuleLayer(LAYER_FUSION, user_permissions_file(), description="Fusion kullanıcı dosyası"),
        RuleLayer(
            LAYER_USER, Path.home() / CLAUDE_USER_SETTINGS, description="Claude kullanıcı ayarı"
        ),
        RuleLayer(
            LAYER_PROJECT,
            root / PROJECT_SETTINGS_PATH,
            requires_trust=True,
            description="Proje ayarı",
        ),
        RuleLayer(
            LAYER_LOCAL,
            root / PROJECT_PERMISSIONS_PATH,
            requires_trust=True,
            description="Proje yerel ayarı",
        ),
    )


def user_permissions_file() -> Path:
    """Fusion'ın kendi izin dosyası."""
    return user_config_dir() / USER_PERMISSIONS_NAME


def _layer_trusted(layer: RuleLayer, root: Path) -> bool:
    if not layer.requires_trust:
        return True
    if layer.name == LAYER_PROJECT:
        return is_project_settings_trusted(root)
    return is_permissions_trusted(root)


def load_permission_rules(
    root: Path,
    *,
    block_reads_outside_root: bool = False,
    block_writes_outside_root: bool = False,
) -> PermissionRuleSet:
    """Tüm katmanları oku; okunamayan ya da güvenilmeyen katman BOŞ sayılır.

    Bozuk dosya izin AÇMAZ (boş liste), ötekileri de düşürmez.
    """
    rules: list[PermissionRule] = []
    untrusted: list[str] = []
    for layer in rule_layers(root):
        if layer.requires_trust and layer.path.is_file() and not _layer_trusted(layer, root):
            untrusted.append(layer.name)
            continue
        rules.extend(read_rules_file(layer.path, source=layer.name))
    return PermissionRuleSet(
        tuple(rules), block_reads_outside_root, block_writes_outside_root, tuple(untrusted)
    )


def read_rules_file(path: Path, *, source: str = "") -> tuple[PermissionRule, ...]:
    """Tek bir ayar dosyasının `permissions.{allow,ask,deny}` listelerini oku."""
    data = _read_json(path)
    permissions = data.get("permissions") if data is not None else None
    if not isinstance(permissions, Mapping):
        return ()
    found: list[PermissionRule] = []
    for decision in PermissionDecision:
        entries = permissions.get(decision.value)
        if not isinstance(entries, list):
            continue
        found.extend(
            rule for entry in entries if (rule := parse_rule(entry, decision, source=source))
        )
    return tuple(found)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# --- Yazıcı ------------------------------------------------------------------- #


def add_rule(path: Path, rule: PermissionRule) -> bool:
    """Kuralı dosyadaki ilgili listeye ekle; zaten varsa `False`. Diğer alanlar korunur."""
    data = _read_json(path) if path.is_file() else {}
    if data is None:
        raise ConfigError(f"İzin dosyası okunamadı ya da JSON değil: {path}")
    permissions = data.get("permissions")
    section = dict(permissions) if isinstance(permissions, Mapping) else {}
    entries = section.get(rule.decision.value)
    current = [e for e in entries if isinstance(e, str)] if isinstance(entries, list) else []
    text = format_rule(rule)
    if text in current:
        return False
    section[rule.decision.value] = [*current, text]
    _write_json(path, {**data, "permissions": section})
    return True


def remove_rule(path: Path, rule: PermissionRule) -> bool:
    """Kuralı dosyadan çıkar; yoksa `False`."""
    data = _read_json(path) if path.is_file() else None
    if data is None:
        return False
    permissions = data.get("permissions")
    if not isinstance(permissions, Mapping):
        return False
    entries = permissions.get(rule.decision.value)
    if not isinstance(entries, list):
        return False
    text = format_rule(rule)
    kept = [e for e in entries if e != text]
    if len(kept) == len(entries):
        return False
    section = {**permissions, rule.decision.value: kept}
    _write_json(path, {**data, "permissions": section})
    return True


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    """Atomik yaz: yarım dosya hiçbir zaman okunmaz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    handle, name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"İzin dosyası yazılamadı ({path}): {exc}") from exc


@dataclass(frozen=True, slots=True)
class RuleRow:
    """RPC/arayüz satırı: kalıp, karar, kaynak katman ve dosya."""

    pattern: str
    decision: str
    source: str
    path: str
    rule: PermissionRule = field(repr=False, compare=False)


def list_rule_rows(root: Path) -> tuple[RuleRow, ...]:
    """Her katmanın kurallarını (güvensiz olanlar dahil, işaretli) satır satır döndür."""
    rows: list[RuleRow] = []
    for layer in rule_layers(root):
        trusted = _layer_trusted(layer, root)
        for rule in read_rules_file(layer.path, source=layer.name):
            source = layer.name if trusted else f"{layer.name} (güvenilmiyor)"
            rows.append(
                RuleRow(format_rule(rule), rule.decision.value, source, str(layer.path), rule)
            )
    return tuple(rows)
