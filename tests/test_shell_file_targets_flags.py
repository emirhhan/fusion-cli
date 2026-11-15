"""Read/Edit deny kuralının kabuğa uygulanması: değer almayan bayraklar ve değişkenli yol (#44).

Bağımsız inceleme (1 Kasım): `_VALUE_FLAGS` komuta bakmadan `-n/-c/-e/-f` sonrasındaki
sözcüğü değer sayıp atıyordu; `cat -n ~/.ssh/id_rsa`, `tail -f .env` kuralsız gibi çalışıyordu.
`$HOME/...` hedefi de sessizce düşüyordu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.config.permission_rules import (
    PermissionDecision,
    PermissionRuleSet,
    parse_rule,
)
from fusion_cli.tools.permission_match import evaluate
from fusion_cli.tools.shell_file_targets import shell_file_targets

ASK = PermissionDecision.ASK
DENY = PermissionDecision.DENY


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    return ev


def _kume(*ciftler: tuple[str, str]) -> PermissionRuleSet:
    kurallar = [parse_rule(m, PermissionDecision(k), source="test") for m, k in ciftler]
    assert all(kurallar)
    return PermissionRuleSet(rules=tuple(k for k in kurallar if k is not None))


def _karar(kume, komut, kok):
    sonuc = evaluate(kume, "run_shell", {"command": komut}, kok)
    return None if sonuc is None else sonuc.decision


@pytest.mark.parametrize(
    "komut",
    [
        "cat -n ~/.ssh/id_rsa",
        "tail -f ~/.ssh/id_rsa",
        "sort -n ~/.ssh/id_rsa",
        "wc -c ~/.ssh/id_rsa",
        "cat -e ~/.ssh/id_rsa",
        "cat $HOME/.ssh/id_rsa",
        "cat ${HOME}/.ssh/id_rsa",
        'cat "$HOME/.ssh/id_rsa"',
        "head -n 3 ~/.ssh/id_rsa",
        "head -n3 ~/.ssh/id_rsa",
        "tail -c 10 ~/.ssh/id_rsa",
    ],
)
def test_degersiz_bayrak_ve_home_hedefi_deny_bulur(tmp_path, komut):
    kume = _kume(("Read(~/.ssh/**)", "deny"))
    assert _karar(kume, komut, tmp_path) is DENY, komut


def test_tail_f_env_deny(tmp_path):
    kume = _kume(("Read(./.env)", "deny"))
    for komut in ("tail -f .env", "cat -e .env", "cat -n .env"):
        assert _karar(kume, komut, tmp_path) is DENY, komut


def test_deger_alan_bayrak_degeri_dosya_sayilmaz():
    assert shell_file_targets("head -n 5 a.txt").reads == ("a.txt",)
    assert shell_file_targets("tail -c 10 a.txt").reads == ("a.txt",)
    assert shell_file_targets("cat -n a.txt").reads == ("a.txt",)
    assert shell_file_targets("sort -k 2 -t , a.txt").reads == ("a.txt",)


def test_cozulemeyen_degiskenli_hedef_kisitlayici_kurali_sorar(tmp_path):
    kume = _kume(("Read(~/.ssh/**)", "deny"))
    assert _karar(kume, "cat $GIZLI_YOL", tmp_path) is ASK
    assert _karar(kume, "cat `echo ~/.ssh/id_rsa`", tmp_path) is ASK
    # Read/Edit kısıtı yoksa değişkenli hedef kural eşleşmesi doğurmaz.
    yalniz_bash = _kume(("Bash(rm *)", "deny"))
    assert _karar(yalniz_bash, "cat $GIZLI_YOL", tmp_path) is None
