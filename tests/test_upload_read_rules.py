"""Chrome yüklemesi `Read(...)` izin kurallarına tabidir (#437)."""

from __future__ import annotations

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.tools.permission_match import evaluate


def _rules(*specs: tuple[str, PermissionDecision]) -> PermissionRuleSet:
    return PermissionRuleSet(
        tuple(parse_rule(text, decision, source="t") for text, decision in specs)
    )


def _upload(value: str) -> dict[str, object]:
    return {"action": "upload", "ref": "e3", "value": value}


def test_read_deny_yuklemeyi_reddeder(tmp_path):
    rules = _rules(("Read(./gizli/**)", PermissionDecision.DENY))
    match = evaluate(rules, "chrome_action", _upload("rapor.pdf, gizli/anahtar.txt"), tmp_path)
    assert match is not None and match.decision is PermissionDecision.DENY


def test_read_ask_yuklemede_sorar(tmp_path):
    rules = _rules(("Read(./*.csv)", PermissionDecision.ASK))
    match = evaluate(rules, "chrome_action", _upload("liste.csv"), tmp_path)
    assert match is not None and match.decision is PermissionDecision.ASK


def test_read_allow_yuklemeyi_genisletmez_ve_esleşmeyen_yol_serbest(tmp_path):
    rules = _rules(
        ("Read(./**)", PermissionDecision.ALLOW), ("Read(./gizli/**)", PermissionDecision.DENY)
    )
    assert evaluate(rules, "chrome_action", _upload("rapor.pdf"), tmp_path) is None


def test_yukleme_disi_eylem_read_kuralina_bakmaz(tmp_path):
    rules = _rules(("Read", PermissionDecision.DENY))
    assert evaluate(rules, "chrome_action", {"action": "click", "ref": "e1"}, tmp_path) is None
    assert evaluate(rules, "chrome_action", _upload("a.txt"), tmp_path) is not None
