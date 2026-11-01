"""Bash allow kuralı: sarmalayıcı soyma, güvenli env, exec sarmalayıcı/find (#58, #72).

Kaynak: https://code.claude.com/docs/en/permissions#wrappers ;
#exec-wrappers-and-find-actions ; #compound-commands ; #what-a-bash-rule-doesnt-match
"""

from __future__ import annotations

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.tools.permission_match import evaluate

ALLOW = PermissionDecision.ALLOW
DENY = PermissionDecision.DENY


def _kume(*ciftler: tuple[str, str]) -> PermissionRuleSet:
    kurallar = []
    for metin, karar in ciftler:
        kural = parse_rule(metin, PermissionDecision(karar), source="test")
        assert kural is not None
        kurallar.append(kural)
    return PermissionRuleSet(rules=tuple(kurallar))


def _karar(kume, komut, kok):
    sonuc = evaluate(kume, "run_shell", {"command": komut}, kok)
    return None if sonuc is None else sonuc.decision


@pytest.mark.parametrize(
    "komut",
    [
        "timeout 30 npm test",
        "timeout -s KILL 30 npm test",
        "time npm test",
        "nice npm test",
        "nice -n 5 npm test",
        "nohup npm test",
        "stdbuf -oL npm test",
        "command npm test",
        "builtin npm test",
        "noglob npm test",
        "NODE_ENV=test npm test",
        "NODE_ENV=test timeout 5 npm test --watch",
    ],
)
def test_sabit_sarmalayicilar_ve_guvenli_env_soyulur(tmp_path, komut):
    assert _karar(_kume(("Bash(npm test *)", "allow")), komut, tmp_path) is ALLOW, komut


@pytest.mark.parametrize(
    "komut",
    [
        "FOO=bar npm test",
        "env npm test",
        "exec npm test",
        "sh -c 'npm test'",
        "sudo npm test",
        "/usr/bin/npm test",
        "command -v npm test",
        "nocorrect npm test",
        "npm test &&",
        "direnv exec . npm test",
    ],
)
def test_allow_bu_bicimleri_karsilamaz(tmp_path, komut):
    assert _karar(_kume(("Bash(npm test *)", "allow")), komut, tmp_path) is None, komut


def test_bayraksiz_xargs_soyulur_bayrakli_soyulmaz(tmp_path):
    kume = _kume(("Bash(grep *)", "allow"))
    assert _karar(kume, "ls | xargs grep x", tmp_path) is ALLOW
    assert _karar(kume, "ls | xargs -n1 grep x", tmp_path) is None


def test_deny_her_atamanin_otesine_gecer(tmp_path):
    assert _karar(_kume(("Bash(rm *)", "deny")), "FOO=bar rm -rf tmp/", tmp_path) is DENY


def test_zincirde_salt_okunur_alt_komut_allow_ister_degil(tmp_path):
    kume = _kume(("Bash(npm test *)", "allow"))
    assert _karar(kume, "git status && npm test", tmp_path) is ALLOW
    assert _karar(kume, "npm test && npm publish", tmp_path) is None
    # Hepsi salt okunursa kural yok: karar kipe kalır.
    assert _karar(kume, "git status && ls", tmp_path) is None


@pytest.mark.parametrize(
    ("kural", "komut"),
    [
        ("Bash(find *)", "find . -exec chmod 777 {} ;"),
        ("Bash(find *)", "find build -type f -delete"),
        ("Bash(find *)", "find . -fprint out.txt"),
        ("Bash(find *)", "find -files0-from list"),
        ("Bash(watch *)", "watch -n 1 date"),
        ("Bash(setsid *)", "setsid sleep 1"),
        ("Bash(ionice *)", "ionice -c3 make"),
        ("Bash(flock *)", "flock /tmp/l make"),
        ("Bash", "find build -delete"),
    ],
)
def test_exec_sarmalayici_ve_find_eylemi_onek_kuraliyla_onaylanmaz(tmp_path, kural, komut):
    assert _karar(_kume((kural, "allow")), komut, tmp_path) is None, komut


def test_birebir_kural_find_eylemini_onaylar(tmp_path):
    kume = _kume(("Bash(find build -type f -delete)", "allow"))
    assert _karar(kume, "find build -type f -delete", tmp_path) is ALLOW
    # `*` içeren komut birebir sayılmaz.
    kume = _kume(("Bash(find . -name *.tmp -delete)", "allow"))
    assert _karar(kume, "find . -name '*.tmp' -delete", tmp_path) is None


def test_find_eylemsiz_onek_kuraliyla_onaylanir(tmp_path):
    assert _karar(_kume(("Bash(find *)", "allow")), "find . -name x", tmp_path) is ALLOW


def test_kural_kumesi_varken_eski_birebir_liste_karar_vermez(tmp_path):
    """#86: settings.local.json iki kez, iki anlamla yorumlanmaz."""
    from fusion_cli.core.tools import Tool
    from fusion_cli.engines.agent.approval import build_request

    kabuk = Tool(
        name="run_shell", description="", parameters={}, run=lambda a, c: None, mutating=True
    )
    eski = frozenset({"git status && rm -rf x"})
    istek = build_request(
        kabuk, {"command": "git status && rm -rf x"}, eski, root=tmp_path, rules=_kume()
    )
    assert istek.pre_allowed is False
    istek = build_request(kabuk, {"command": "git status && rm -rf x"}, eski, root=tmp_path)
    assert istek.pre_allowed is True
