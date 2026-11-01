"""Kanca yükünde araç girdisi/çıktısı: Fusion argümanı ↔ Claude Code araç şeması.

Claude betikleri `tool_input`'u Claude adlarıyla okur: Bash `{command, run_in_background}`,
Write `{file_path, content}`, Edit `{file_path, old_string, new_string, replace_all}`; dosya
araçlarında `file_path` HER ZAMAN mutlaktır. `updatedInput` girdinin TAMAMINI değiştirir
(Claude ile aynı: değişmeyen alanlar da yazılmalı); geri çevrilirken Claude adları Fusion
adlarına döner, mutlak yol özgün göreli yolla aynı dosyaysa özgün yazım korunur.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ...core.tools import ToolFamily, tool_family

#: `path` argümanı Claude'da mutlak `file_path` olan dosya araçları.
_FILE_TOOLS = frozenset({"read_file", "view_file", "write_file", "edit_file", "multi_edit"})
#: Araç başına Fusion → Claude argüman adı (dosya yolu ayrıca çevrilir).
_EDIT_KEYS = {"old": "old_string", "new": "new_string"}
_SHELL_KEYS = {"background": "run_in_background"}
_FUSION_PATH = "path"
_CLAUDE_PATH = "file_path"


def _key_map(tool_name: str) -> dict[str, str]:
    if tool_name == "edit_file":
        return _EDIT_KEYS
    if tool_family(tool_name) is ToolFamily.SHELL:
        return _SHELL_KEYS
    return {}


def _absolute(root: Path, raw: str) -> str:
    path = Path(raw).expanduser()
    return str(path if path.is_absolute() else (root / path).resolve(strict=False))


def _rename(values: Mapping[str, object], names: Mapping[str, str]) -> dict[str, object]:
    return {names.get(key, key): value for key, value in values.items()}


def claude_tool_input(tool_name: str, args: Mapping[str, object], root: Path) -> dict[str, object]:
    """Fusion argümanlarını Claude aracının `tool_input` şekline çevir."""
    tool_input = _rename(args, _key_map(tool_name))
    edits = args.get("edits")
    if tool_name == "multi_edit" and isinstance(edits, list):
        tool_input["edits"] = [
            _rename(item, _EDIT_KEYS) if isinstance(item, Mapping) else item for item in edits
        ]
    raw = args.get(_FUSION_PATH)
    if tool_name in _FILE_TOOLS and isinstance(raw, str):
        tool_input.pop(_FUSION_PATH, None)
        tool_input[_CLAUDE_PATH] = _absolute(root, raw)
    elif isinstance(raw, str) and _CLAUDE_PATH not in tool_input:
        # Eski betikler için: dosya aracı olmayan yol argümanının da `file_path` takma adı.
        tool_input[_CLAUDE_PATH] = raw
    return tool_input


def fusion_tool_args(
    tool_name: str,
    original: Mapping[str, object],
    updated: Mapping[str, object],
    root: Path,
) -> dict[str, object]:
    """`updatedInput`'u (girdinin tamamı) Fusion argümanına geri çevir."""
    reverse = {claude: fusion for fusion, claude in _key_map(tool_name).items()}
    arguments = _rename(updated, reverse)
    edits = updated.get("edits")
    if tool_name == "multi_edit" and isinstance(edits, list):
        back = {claude: fusion for fusion, claude in _EDIT_KEYS.items()}
        arguments["edits"] = [
            _rename(item, back) if isinstance(item, Mapping) else item for item in edits
        ]
    claude_path = arguments.pop(_CLAUDE_PATH, None)
    if not isinstance(claude_path, str) or _FUSION_PATH in arguments:
        return arguments
    if _FUSION_PATH not in original and tool_name not in _FILE_TOOLS:
        arguments[_CLAUDE_PATH] = claude_path
        return arguments
    previous = original.get(_FUSION_PATH)
    same = isinstance(previous, str) and _absolute(root, previous) == _absolute(root, claude_path)
    arguments[_FUSION_PATH] = previous if same else claude_path
    return arguments


def claude_tool_response(
    tool_name: str, tool_input: Mapping[str, object], output: str
) -> dict[str, object]:
    """PostToolUse `tool_response`: Claude aracının çıktı şekli (bilinmeyen araçta genel)."""
    file_path = tool_input.get(_CLAUDE_PATH)
    if tool_family(tool_name) is ToolFamily.SHELL:
        return {"stdout": output, "stderr": "", "interrupted": False, "isImage": False}
    if tool_name == "write_file" and isinstance(file_path, str):
        return {"filePath": file_path, "content": tool_input.get("content", ""), "output": output}
    if tool_name == "edit_file" and isinstance(file_path, str):
        return {
            "filePath": file_path,
            "oldString": tool_input.get("old_string", ""),
            "newString": tool_input.get("new_string", ""),
            "replaceAll": bool(tool_input.get("replace_all", False)),
            "output": output,
        }
    if tool_name in ("read_file", "view_file") and isinstance(file_path, str):
        return {"type": "text", "file": {"filePath": file_path, "content": output}}
    return {"output": output, "success": True}
