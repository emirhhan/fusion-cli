"""Ayar dosyalarında atlanan izin kurallarının uyarısı (#87).

Claude Code ayar dosyasındaki parantezli `mcp__…(…)` kuralını yüklemez ve geçersiz ayar
olarak bildirir. Fusion aynı kuralı atlar; bu modül başlangıçta ve `fusion doctor`da
gösterilecek satırları üretir.
"""

from __future__ import annotations

from pathlib import Path

from .permission_rules import rule_layers, skipped_settings_rules

SKIPPED_RULES_WARNING = (
    "İzin kuralı yüklenmedi ({path}): {rules} — MCP kuralı belirteç almaz; "
    "mcp__sunucu ya da mcp__sunucu__araç yaz."
)


def skipped_rule_warnings(root: Path) -> tuple[str, ...]:
    """Her katmanda atlanan kurallar için bir uyarı satırı."""
    lines: list[str] = []
    for layer in rule_layers(root):
        skipped = skipped_settings_rules(layer.path)
        if skipped:
            lines.append(SKIPPED_RULES_WARNING.format(path=layer.path, rules=", ".join(skipped)))
    return tuple(lines)
