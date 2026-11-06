"""Exact harness identities whose receipts do not witness business data reads."""

DISCOVERY_METADATA_NAMES = frozenset({"DiscoverMcpTools", "WaitForMcpServers", "ToolSearch"})
OPAQUE_DELEGATION_NAMES = frozenset(
    {"Agent", "Task", "invoke_agent", "spawn_agent", "spawn_agents", "invoke_subagent"}
)


def data_count_witness(name: str) -> bool:
    """A remote tool with a similar name remains a normal business operation."""
    return name not in DISCOVERY_METADATA_NAMES | OPAQUE_DELEGATION_NAMES
