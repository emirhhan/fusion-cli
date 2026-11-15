"""Claude Code `.claude/launch.json` biçiminin ayrıntıları (#440).

Belge (desktop › .claude/launch.json): dosya yorumlu JSON'u destekler; `program` + `args`
doğrudan `node` ile çalışan betiktir; `port` varsayılanı 3000; `cwd` `${workspaceFolder}`
ile proje köküne başvurabilir; port değişince `runtimeArgs` içindeki `--port`/`-p` değeri
yeniden yazılır; üst düzey `autoVerify` varsayılan açıktır.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Komutlu yapılandırmada `port` yazılmadıysa (Claude Code: "Defaults to 3000").
DEFAULT_PORT = 3000
WORKSPACE_FOLDER = "${workspaceFolder}"
_PORT_FLAGS = ("--port", "-p")


def strip_json_comments(text: str) -> str:
    """`//` ve `/* */` yorumlarını dize dışında sil (JSON with comments)."""
    out: list[str] = []
    index, length = 0, len(text)
    in_string = False
    while index < length:
        char = text[index]
        if in_string:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 2
                continue
            in_string = char != '"'
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = length if end < 0 else end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


def program_command(program: str, args: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    """`program` + `args` → (`node`, (betik, *args))."""
    return "node", (program, *args)


def workspace_relative(cwd: str) -> str:
    """`${workspaceFolder}/web` → `web`; `${workspaceFolder}` → `` (proje kökü)."""
    return cwd.replace(WORKSPACE_FOLDER, "").replace("\\", "/").strip("/")


def rewrite_port_flags(args: Sequence[str], port: int) -> tuple[str, ...]:
    """`--port 3000`, `-p 3000`, `--port=3000` değerlerini seçilen portla değiştir."""
    result = list(args)
    for index, arg in enumerate(result):
        if arg in _PORT_FLAGS and index + 1 < len(result) and result[index + 1].isdigit():
            result[index + 1] = str(port)
        elif arg.startswith("--port=") and arg.removeprefix("--port=").isdigit():
            result[index] = f"--port={port}"
    return tuple(result)
