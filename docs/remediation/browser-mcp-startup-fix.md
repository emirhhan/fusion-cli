# Browser-only MCP startup — NEEDS REVIEW

## Root and boundary

The per-turn path is confirmed in `cli/session.py::_run_agent_with_mcp`: configured `mcp_servers` trigger `ensure_mcp_tools` before the runner applies its allowed tool surface. An unrelated configured connector can therefore delay a browser task whose tools cannot be called. `McpConnectionService.__init__` only initializes state; it does not establish these connections.

Chrome's `claude-in-chrome__*` aliases are native tools registered by `tools/builtin.py::build_registry`; their MCP-shaped names do not require an external MCP server. The panel code surface also permits `ask_teacher`, registered locally by `engine_tools.py`. Pending skill restrictions intersect this surface.

## Current change

`AppSession._run_turn` computes the allowed tool surface once. Only for a browser-only surface entirely within the built-in registry plus local `ask_teacher`, it passes `bootstrap_mcp=False` to `run_agent_task`. This new flag defaults to true and is forwarded to `_run_agent_with_mcp`, where it controls MCP bootstrap and MCP reference expansion. Normal main turns and future external/unknown tool surfaces retain connector startup. Hosted connector settings are unchanged.

The original full Config, including every configured server's credential environment-name metadata, reaches runtime settings, AgentDeps and model/runner configuration unchanged. The skip decision does not remove or copy credentials. In particular, `apply_runtime_settings` still derives `hidden_env` from all configured `env_names` and `token_env`, so the code-mode panel's `run_shell` child environment retains its credential exclusions.

## Security review correction

Initial commit `6954a28a` implemented the skip by replacing Config with `mcp_servers=()`. The independent review correctly identified that this also removed the metadata used to scrub shell-child environments. That approach is superseded by the separate bootstrap flag. A regression first reproduced the missing exclusion using only synthetic environment names/values; the corrected test now exercises actual AppSession → run_agent_task → _run_agent_with_mcp → fake runner plumbing, actual runtime settings and actual `_shell_env`. It never launches a shell, connector or model.

## Verification

All profiles, connector configuration and environment values are synthetic temporary fixtures. No live secrets, network, model, UI or native desktop action were used.

- Browser startup suite: **4 passed**. Both code/chat surfaces keep native aliases and the original configured servers while explicitly skipping bootstrap. Normal turns and a synthetic external future surface retain bootstrap.
- The integration regression uses multiple fake `env_names` and a fake `token_env`, checks every name is excluded from actual shell-child environments for browser/main/external turns, and confirms a public marker survives. It checks original Config identity at the browser runner, shell/native alias availability, and actual mocked connector-start counts of zero after the browser turn, one after main, and two after external fallback. Existing negative startup assertions remain enforced.
- Combined browser/ownership/submission/CLI session/MCP notice/environment scrub/runtime-context suite: **62 passed**.
- Scoped ruff, scoped mypy and source/test whitespace checks passed.

No new live latency or UI acceptance claim is made. Parent will arrange independent general/Python re-review. No build, installation or unrelated scope change was performed.
