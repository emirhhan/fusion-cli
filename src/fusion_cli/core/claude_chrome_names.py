"""Claude in Chrome araç adları (#431).

Claude Code'da tarayıcı araçları `claude-in-chrome` MCP sunucusundan gelir ve
`mcp__claude-in-chrome__<araç>` adını taşır. Fusion MCP araçlarını `sunucu__araç`
biçiminde adlandırır; izin kuralı `mcp__claude-in-chrome__computer` ve kanca eşleştiricisi
bu adı aynen tanır (`tools/permission_match`). Yalnız stdlib: çekirdek katmanı.
"""

from __future__ import annotations

#: Fusion içindeki ad öneki (Claude'daki `mcp__` öneki olmadan, diğer MCP araçları gibi).
CLAUDE_CHROME_SERVER = "claude-in-chrome"
CLAUDE_CHROME_PREFIX = f"{CLAUDE_CHROME_SERVER}__"

#: Sayfayı yalnız okuyan araçlar (değiştirici değil).
CLAUDE_CHROME_READ = (
    "read_page",
    "find",
    "get_page_text",
    "read_console_messages",
    "read_network_requests",
    "tabs_context_mcp",
    "shortcuts_list",
    "list_connected_browsers",
    "select_browser",
    "switch_browser",
)
#: Sayfayla etkileşen araçlar.
CLAUDE_CHROME_ACT = (
    "navigate",
    "computer",
    "form_input",
    "tabs_create_mcp",
    "tabs_close_mcp",
    "gif_creator",
    "shortcuts_execute",
    "javascript_tool",
    "file_upload",
    "upload_image",
    "resize_window",
    "browser_batch",
)
#: Her istekte sunulan çekirdek araçlar; kalanı yalnız Chrome/masaüstü işinde (istem bütçesi).
CLAUDE_CHROME_CORE = (
    "navigate",
    "read_page",
    "find",
    "form_input",
    "computer",
    "get_page_text",
    "tabs_context_mcp",
)


def claude_chrome_name(short: str) -> str:
    """`navigate` → `claude-in-chrome__navigate`."""
    return f"{CLAUDE_CHROME_PREFIX}{short}"


CLAUDE_CHROME_TOOL_NAMES = frozenset(
    claude_chrome_name(short) for short in (*CLAUDE_CHROME_READ, *CLAUDE_CHROME_ACT)
)
#: Yalnız Chrome/masaüstü işinde sunulanlar.
CLAUDE_CHROME_SCOPED = frozenset(
    claude_chrome_name(short)
    for short in (*CLAUDE_CHROME_READ, *CLAUDE_CHROME_ACT)
    if short not in CLAUDE_CHROME_CORE
)


def claude_chrome_short(name: str) -> str | None:
    """Tam ya da kısa (`computer`, `mcp__claude-in-chrome__computer`) adın kısa hâli."""
    for prefix in (f"mcp__{CLAUDE_CHROME_PREFIX}", CLAUDE_CHROME_PREFIX):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    known = (*CLAUDE_CHROME_READ, *CLAUDE_CHROME_ACT)
    return name if name in known else None
