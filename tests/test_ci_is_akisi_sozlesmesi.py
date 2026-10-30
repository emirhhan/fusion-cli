"""CI iş akışı sözleşmesi: sır taraması ve bağımlılık denetimi var, hiçbir iş sınırsız çalışmaz."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return loaded


def test_sir_taramasi_ve_bagimlilik_denetimi_tanimli() -> None:
    """Q1-06. Ölçüldü (30 Ekim): `.gitleaks.toml` vardı, hiçbir iş gitleaks/audit koşmuyordu."""
    jobs = _load("security.yml")["jobs"]
    assert {"gitleaks", "python-audit", "npm-audit", "cargo-audit"} <= set(jobs)
    uses = [step.get("uses", "") for step in jobs["gitleaks"]["steps"]]
    assert any(item.startswith("gitleaks/gitleaks-action") for item in uses)
    assert (WORKFLOWS.parent / "dependabot.yml").is_file()


def test_her_isin_zaman_asimi_var() -> None:
    """Q1-26: takılan iş 6 saatlik varsayılanı yakmasın (yeniden kullanılan iş çağrıları hariç)."""
    eksik = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for name, job in _load(path.name)["jobs"].items():
            if "uses" not in job and "timeout-minutes" not in job:
                eksik.append(f"{path.name}:{name}")
    assert eksik == []
