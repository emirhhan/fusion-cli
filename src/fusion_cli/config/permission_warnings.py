"""Ayar dosyalarında atlanan izin kurallarının uyarısı (#87).

Claude Code ayar dosyasındaki parantezli `mcp__…(…)` kuralını yüklemez ve geçersiz ayar
olarak bildirir. Fusion aynı kuralı atlar; bu modül başlangıçta ve `fusion doctor`da
gösterilecek satırları üretir.
"""

from __future__ import annotations

from pathlib import Path

from .permission_rules import (
    read_rules_file,
    rule_layers,
    skipped_settings_rules,
    user_permissions_file,
    user_rule_file,
)

SKIPPED_RULES_WARNING = (
    "İzin kuralı yüklenmedi ({path}): {rules} — MCP kuralı belirteç almaz; "
    "mcp__sunucu ya da mcp__sunucu__araç yaz."
)


LEGACY_USER_FILE_WARNING = (
    "{old} kullanımdan kalktı: kuralları bu sürüm boyunca okunur, yeni kurallar Claude Code "
    "gibi {new} dosyasına yazılır. Kuralları oraya taşıyıp eski dosyayı sil (#66)."
)


def skipped_rule_warnings(root: Path) -> tuple[str, ...]:
    """Her katmanda atlanan kurallar ve eski Fusion kullanıcı dosyası için uyarı satırları."""
    lines: list[str] = []
    legacy = user_permissions_file()
    if legacy.is_file() and read_rules_file(legacy):
        lines.append(LEGACY_USER_FILE_WARNING.format(old=legacy, new=user_rule_file()))
    for layer in rule_layers(root):
        skipped = skipped_settings_rules(layer.path)
        if skipped:
            lines.append(SKIPPED_RULES_WARNING.format(path=layer.path, rules=", ".join(skipped)))
    return tuple(lines)
