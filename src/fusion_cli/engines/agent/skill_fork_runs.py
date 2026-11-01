"""Arka planda koşan `context: fork` beceri çağrılarının kaydı (Claude Code #141).

Belge (code.claude.com/docs/en/skills, "Run skills in a subagent"): fork becerisi varsayılan
olarak arka planda koşar, ama aynı becerinin önceki çağrısı hâlâ sürerken Claude Code yeni
çağrının sonucunu BEKLER (`background: false` olmasa da). Kayıt oturumun `ChildRuns`
nesnesine bağlıdır (zayıf başvuru): oturum kapanınca kendiliğinden düşer, alt ajanlara
devredilen aynı nesne üzerinden derinlikler arası da görünür.
"""

from __future__ import annotations

import json
from weakref import WeakKeyDictionary

#: `ChildRuns` → {beceri adı: son arka plan ajan kimliği}.
_RUNS: WeakKeyDictionary[object, dict[str, str]] = WeakKeyDictionary()


def _registry(deps: object) -> dict[str, str] | None:
    runs = getattr(deps, "child_runs", None)
    if runs is None:
        return None
    try:
        return _RUNS.setdefault(runs, {})
    except TypeError:
        # Zayıf başvuru almayan sahte nesne (ör. SimpleNamespace): kayıt tutulmaz.
        return None


def previous_running(deps: object, skill: str) -> bool:
    """Bu becerinin önceki arka plan çağrısı hâlâ sürüyor mu?"""
    if not skill:
        return False
    registry = _registry(deps)
    identifier = registry.get(skill, "") if registry is not None else ""
    if not identifier:
        return False
    running = getattr(getattr(deps, "child_runs", None), "running", None)
    return bool(callable(running) and running(identifier))


def remember(deps: object, skill: str, receipt: str) -> None:
    """`launch_agent` makbuzu arka plan başlangıcıysa ajan kimliğini beceriye bağla."""
    if not skill:
        return
    registry = _registry(deps)
    if registry is None:
        return
    try:
        data = json.loads(receipt)
    except (TypeError, ValueError):
        return
    if not isinstance(data, dict) or data.get("status") != "async_launched":
        return
    identifier = data.get("agentId")
    if isinstance(identifier, str) and identifier:
        registry[skill] = identifier
