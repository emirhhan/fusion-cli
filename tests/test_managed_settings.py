"""Claude yönetilen (managed) ayar katmanı: kurallar, öncelik, allowManagedPermissionRulesOnly (#65)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fusion_cli.config import permission_settings as ps
from fusion_cli.config.managed_settings import (
    managed_permission_rules_only,
    managed_settings_data,
    managed_settings_files,
)
from fusion_cli.config.permission_admin import is_rule_removable
from fusion_cli.config.permission_rules import (
    LAYER_MANAGED,
    PermissionDecision,
    PermissionRule,
    list_rule_rows,
    load_permission_rules,
    set_session_rules,
)


def _yaz(path: Path, data: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def managed() -> Path:
    folder = Path(os.environ["FUSION_CLAUDE_MANAGED_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@pytest.fixture(autouse=True)
def _oturum_kurallari_temiz():
    set_session_rules(())
    yield
    set_session_rules(())


def _kalip(rules: tuple[PermissionRule, ...], decision: PermissionDecision) -> set[str]:
    return {f"{r.tool}({r.specifier})" if r.specifier else r.tool for r in rules if r.decision is decision}


def test_yonetilen_dosya_yoksa_katman_bos(tmp_path: Path) -> None:
    assert managed_settings_files() == ()
    assert managed_settings_data() == {}
    assert load_permission_rules(tmp_path).rules == ()


def test_yonetilen_deny_kurali_yuklenir_ve_kaynak_yonetilen(managed: Path, tmp_path: Path) -> None:
    _yaz(managed / "managed-settings.json", {"permissions": {"deny": ["WebFetch"]}})

    rules = load_permission_rules(tmp_path).rules

    assert [(r.tool, r.source) for r in rules] == [("WebFetch", LAYER_MANAGED)]


def test_dropin_parcalari_alfabetik_birlesir(managed: Path) -> None:
    _yaz(managed / "managed-settings.json", {"permissions": {"deny": ["WebFetch"]}, "x": 1})
    _yaz(managed / "managed-settings.d" / "20-b.json", {"permissions": {"deny": ["Bash(rm *)"]}, "x": 3})
    _yaz(managed / "managed-settings.d" / "10-a.json", {"x": 2})

    data = managed_settings_data()

    assert data["x"] == 3
    assert data["permissions"] == {"deny": ["WebFetch", "Bash(rm *)"]}


def test_yonetilen_satirlar_listelenir_ama_silinemez(managed: Path, tmp_path: Path) -> None:
    _yaz(managed / "managed-settings.json", {"permissions": {"allow": ["Bash(ls *)"]}})

    rows = list_rule_rows(tmp_path)

    assert [(row.pattern, row.source) for row in rows] == [("Bash(ls *)", LAYER_MANAGED)]
    assert is_rule_removable(tmp_path, LAYER_MANAGED) is False


def test_yalniz_yonetilen_kurallari_kullanici_ve_proje_kurallarini_dusurur(
    managed: Path, tmp_path: Path
) -> None:
    _yaz(
        managed / "managed-settings.json",
        {"allowManagedPermissionRulesOnly": True, "permissions": {"allow": ["Bash(git status *)"]}},
    )
    _yaz(Path.home() / ".claude" / "settings.json", {"permissions": {"allow": ["Bash(*)"], "deny": ["Read"]}})
    _yaz(tmp_path / ".claude" / "settings.json", {"permissions": {"ask": ["Edit"]}})
    set_session_rules(
        [
            PermissionRule("Bash", "npm *", PermissionDecision.ALLOW),
            PermissionRule("WebSearch", None, PermissionDecision.DENY),
        ]
    )

    assert managed_permission_rules_only() is True
    rules = load_permission_rules(tmp_path).rules

    assert _kalip(rules, PermissionDecision.ALLOW) == {"Bash(git status *)"}
    assert _kalip(rules, PermissionDecision.ASK) == set()
    # Komut satırı deny'ı belge dışı; gevşetilmez.
    assert _kalip(rules, PermissionDecision.DENY) == {"WebSearch"}


def test_bayrak_yonetilen_disinda_etkisiz(managed: Path, tmp_path: Path) -> None:
    _yaz(
        Path.home() / ".claude" / "settings.json",
        {"allowManagedPermissionRulesOnly": True, "permissions": {"allow": ["Bash(ls *)"]}},
    )

    assert managed_permission_rules_only() is False
    assert _kalip(load_permission_rules(tmp_path).rules, PermissionDecision.ALLOW) == {"Bash(ls *)"}


def test_yonetilen_defaultmode_en_yuksek_oncelik_ve_bypass_gecerli(
    managed: Path, tmp_path: Path
) -> None:
    _yaz(Path.home() / ".claude" / "settings.json", {"permissions": {"defaultMode": "acceptEdits"}})
    _yaz(managed / "managed-settings.json", {"permissions": {"defaultMode": "bypassPermissions"}})

    assert ps.default_mode_setting(tmp_path) == "bypassPermissions"


def test_yonetilen_disable_bypass_ve_auto(managed: Path, tmp_path: Path) -> None:
    _yaz(
        managed / "managed-settings.json",
        {"permissions": {"disableBypassPermissionsMode": "disable", "disableAutoMode": "disable"}},
    )

    assert ps.bypass_mode_disabled(tmp_path) is True
    assert ps.auto_mode_disabled(tmp_path) is True


def test_mdm_profili_dosya_tabanli_ayarin_ustunde(managed: Path, tmp_path: Path) -> None:
    import plistlib

    _yaz(managed / "managed-settings.json", {"permissions": {"defaultMode": "plan"}})
    with (managed / "com.anthropic.claudecode.plist").open("wb") as handle:
        plistlib.dump({"permissions": {"defaultMode": "acceptEdits", "deny": ["WebFetch"]}}, handle)

    assert ps.default_mode_setting(tmp_path) == "acceptEdits"
    assert _kalip(load_permission_rules(tmp_path).rules, PermissionDecision.DENY) == {"WebFetch"}
