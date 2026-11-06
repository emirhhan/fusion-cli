"""Exact harness identities whose receipts do not witness business data reads."""

DISCOVERY_METADATA_NAMES = frozenset({"DiscoverMcpTools", "WaitForMcpServers", "ToolSearch"})
OPAQUE_DELEGATION_NAMES = frozenset(
    {"Agent", "Task", "invoke_agent", "spawn_agent", "spawn_agents", "invoke_subagent"}
)
