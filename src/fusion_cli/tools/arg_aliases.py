"""Başka araç takımlarının ad ve argüman sözleşmelerini Fusion'ınkine çevir.

Ölçüldü (30 Ekim): takma adlar yalnız ARAÇ adını değiştiriyordu. Claude Code'a alışık
bir model `Edit {file_path, old_string, new_string}` ya da Windsurf'ün `view_file
{AbsolutePath}` çağrısını yapınca `require_str(args, "path")` "alan eksik" diyor, model
aynı adlarla ısrar ediyor ve tur boşa gidiyordu.

Eşleme DAR ve güvenlidir: yalnız aracın şemasında hedef alan VARSA, kaynak anahtar şemada
YOKSA ve hedef alan çağrıda zaten verilmemişse yapılır. Aracın kendi anahtarına dokunulmaz.
"""

from __future__ import annotations

import re

from ..core.tools import Tool, ToolArgs

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

#: normalleştirilmiş kaynak anahtar -> Fusion alanı
ARGUMENT_ALIASES: dict[str, str] = {
    "file_path": "path",
    "filepath": "path",
    "filename": "path",
    "file_name": "path",
    "file": "path",
    "target_file": "path",
    "absolute_path": "path",
    "absolutepath": "path",
    "directory_path": "path",
    "dir_path": "path",
    "directory": "path",
    "old_string": "old",
    "old_str": "old",
    "old_text": "old",
    "new_string": "new",
    "new_str": "new",
    "new_text": "new",
    "cmd": "command",
    "command_line": "command",
    "commandline": "command",
    "file_text": "content",
    "file_content": "content",
    "contents": "content",
    "search_query": "query",
}


def normalize_name(name: str) -> str:
    """`ReadFile`, `read-file`, `READ_FILE` -> `read_file`."""
    snake = _CAMEL_BOUNDARY.sub("_", name.strip())
    return snake.lower().replace("-", "_").replace(" ", "_")


def adapt_arguments(tool: Tool, args: ToolArgs) -> ToolArgs:
    """Şemada olmayan yabancı anahtarları aracın alanlarına eşle; yeni sözlük döndür."""
    properties = tool.parameters.get("properties")
    if not isinstance(properties, dict) or not properties:
        return args
    adapted: dict[str, object] = dict(args)
    for key in list(args):
        if key in properties:
            continue
        target = ARGUMENT_ALIASES.get(normalize_name(key))
        if target is not None and target in properties and target not in adapted:
            adapted[target] = adapted.pop(key)
    return adapted
