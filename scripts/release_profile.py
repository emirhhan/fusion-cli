"""Project the explicit repository acceptance profile without loading user settings/keys."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.effective_config import project_effective
from evals.frozen_engine import require_protected_profile
from evals.loader import load_tasks
from evals.profiles import _digest_entries
from scripts.release_manifest import ROOT, sha256_file


def profile_facts(path: Path) -> dict[str, str]:
    # These constructors parse supplied mappings only; do not call load_config,
    # load_environment, key detection, plugin discovery, or the credential store.
    from fusion_cli.config.loader import _assemble, _deep_merge, _read_yaml

    config = _assemble(
        _deep_merge(_read_yaml(ROOT / "src/fusion_cli/config/defaults.yaml"), _read_yaml(path)),
        path,
    )
    require_protected_profile(config, platform="darwin")
    effective = project_effective(config, config.agent, "general")
    task_config = _digest_entries([effective.digest])
    tasks = load_tasks(ROOT / "evals/suite/production.yaml")
    return {
        "model": config.agent.model,
        "config_file_sha256": sha256_file(path),
        "effective_config_digest": _digest_entries(
            sorted((task.id, task_config) for task in tasks)
        ),
        "task_config_digest": task_config,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    print(json.dumps(profile_facts(args.config), sort_keys=True))


if __name__ == "__main__":
    main()
