"""MCP araç açıklamalarını Fusion'ın onay etki sınıfına çevir.

MCP şartnamesine göre açıklamalar İPUCUDUR ve güvenilmeyen sunucuya dayanarak
gevşek karar verilmez. Bu yüzden ipucu yalnız onayı SIKILAŞTIRMAK için kullanılır;
tek istisna `readOnlyHint`: auto kip bugün zaten bütün uzak araçları sormadan
çalıştırıyordu, salt okunur araç için bu davranış korunur. Security kip hepsini
yine sorar.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

from ..core.tools import ToolEffect


def effect_from_annotations(annotations: ToolAnnotations | None) -> ToolEffect:
    """Açıklaması olmayan araç yazma sayılır; `destructiveHint` açıkça true ise yıkıcı.

    Şartnamenin varsayılanı `destructiveHint=true`'dur; açıklamasız her aracı yıkıcı
    saymak auto kipte eski sunucuların (ör. Godot MCP) HER çağrısını sorar ve
    otonom koşuları kullanılamaz kılar. Açıklamasız araç oturum başına bir kez sorulur.
    """
    if annotations is None:
        return ToolEffect.REMOTE_WRITE
    if annotations.readOnlyHint is True:
        return ToolEffect.REMOTE_READ
    if annotations.destructiveHint is True:
        return ToolEffect.REMOTE_DESTRUCTIVE
    return ToolEffect.REMOTE_WRITE
