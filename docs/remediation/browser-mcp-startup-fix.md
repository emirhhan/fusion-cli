# Browser-only MCP startup — NEEDS REVIEW

## Root and boundary

The per-turn path is confirmed in `cli/session.py::_run_agent_with_mcp`: configured `mcp_servers` trigger `ensure_mcp_tools` before the runner applies its allowed tool surface. That means an unrelated configured connector can delay a browser task even though its tools cannot be called. `McpConnectionService.__init__` only initializes state; it does not establish these connections. This fix therefore targets the turn's actual connector-startup input.

Chrome's `claude-in-chrome__*` aliases are native tools registered by `tools/builtin.py::build_registry`; their MCP-shaped names do not require an external MCP server. The panel's code-mode surface additionally permits `ask_teacher`, registered locally by `engine_tools.py`. Pending skill tool restrictions intersect the surface and cannot add external tools.

## Change

`AppSession._run_turn` computes the allowed tool surface once. For `browser_only` execution with configured MCP servers, it verifies every allowed name against the built-in registry plus the local `ask_teacher` tool. When all names are local, only the runner's configuration is replaced with `replace(config, mcp_servers=())`. The session's persisted/in-memory configuration remains unchanged, as does the next normal main turn. A future surface containing an external or unknown name retains its configured MCP servers. Native Chrome aliases and existing tool restrictions remain intact. Hosted connector settings are outside this change.

## Verification

Tests use temporary synthetic profiles, a fake connector configuration and mocked `run_agent_task`; no connector, model or network call is performed.

- `tests/test_session_browser_mcp_startup.py`: code/chat cases first failed because the browser runner still received the fake connector; final **3 passed**. They verify the browser runner receives no MCP servers, keeps native Chrome aliases, retains the persisted config, and leaves the next normal turn's server intact. A synthetic external tool surface verifies the conservative fallback.
- Combined browser-MCP/ownership/submission suite: **39 passed**.
- Existing targeted Chrome panel/session integration cases: **5 passed**.
- Scoped ruff, scoped mypy and source/test `git diff --check` passed.

The startup bypass follows directly from the confirmed `_run_agent_with_mcp` configuration branch. No new live latency or UI acceptance claim is made. Parent will arrange independent general/Python review. No build, installation or other scope changes were performed.
