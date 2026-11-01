"""`fusion doctor` ayar dosyası doğrulaması ve Remote Control uygunluğu (#309).

Claude Code `claude doctor` kurulum sağlığının yanında ayar dosyalarındaki doğrulama
hatalarını ve Remote Control uygunluğunu da raporlar. Burada Claude biçimindeki ayar
dosyaları (`~/.claude/settings.json`, projenin `.claude/settings.json` ve
`.claude/settings.local.json`, Fusion'ın `permissions.json`'ı) salt okunur denetlenir:
geçersiz JSON, kök nesne olmayan dosya ve çözülemeyen izin kuralı ayrı satır olur.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config.permission_rules import PermissionDecision, parse_rule, rule_layers
from .doctor import Check

_SETTINGS_REMEDY = "Dosyadaki hatayı düzeltin; bozuk kural yok sayılır ve izin AÇMAZ."


def settings_checks(root: Path) -> list[Check]:
    """Var olan her ayar katmanı için bir satır; hata yoksa geçti."""
    checks: list[Check] = []
    for layer in rule_layers(root):
        if not layer.path.is_file():
            continue
        problems = _problems(layer.path)
        checks.append(
            Check(
                name=f"Ayar dosyası ({layer.name})",
                value="; ".join(problems) if problems else f"geçerli: {layer.path}",
                ok=not problems,
                remedy=f"{layer.path}: {_SETTINGS_REMEDY}" if problems else "",
            )
        )
    return checks


def _problems(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"okunamadı: {error}"]
    if not isinstance(data, dict):
        return ["kök bir JSON nesnesi olmalı"]
    block = data.get("permissions")
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["permissions bir nesne olmalı"]
    problems: list[str] = []
    for decision in PermissionDecision:
        entries = block.get(decision.value)
        if entries is None:
            continue
        if not isinstance(entries, list):
            problems.append(f"permissions.{decision.value} bir liste olmalı")
            continue
        bad = [str(entry) for entry in entries if parse_rule(entry, decision) is None]
        if bad:
            problems.append(f"permissions.{decision.value}: geçersiz kural {', '.join(bad)}")
    return problems


def remote_control_check() -> Check:
    """Remote Control (`fusion remote-control`) bu kurulumda çalışabilir mi."""
    try:
        from ..remote.constants import DEFAULT_REMOTE_PORT
        from . import remote_control  # noqa: F401  (içe aktarılabilirlik denetimi)
    except ImportError as error:
        return Check(
            name="Remote Control",
            value=f"kullanılamaz: {error}",
            ok=False,
            remedy="Eksik bağımlılığı kurun (fusion update) ya da kurulumu onarın.",
        )
    return Check(name="Remote Control", value=f"uygun (varsayılan port {DEFAULT_REMOTE_PORT})")
