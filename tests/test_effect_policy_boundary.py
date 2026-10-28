"""Komut adından güvenlik çıkarılmaz: kip bazlı karar matrisi (T1-01, T1-03, T1-04, T1-05).

Ölçüldü (28 Ekim): kod çalıştıran bir awk ifadesi ve dosya yazan bir sed ifadesi
salt-okur sayıldı (Plan/Manuel kipte sorulmadan çalışır); `git branch -D` salt-okur
sayıldı ve salt-okur `git` aracından onaysız geçiyordu; `git stash drop` edits
kipinde gözetimsiz uygundu; `npm run deploy` ve `curl --json` edits kipinin beyaz
listesinden geçiyordu (otomatik kipin risk denetimi ikisini zaten yakalıyordu).
Meşru okuma ve proje içi düzenleme ise gereksiz onay üretmemeli.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.auto_policy import auto_risk, is_read_only_command
from fusion_cli.tools.command_policy import is_unattended_safe
from fusion_cli.tools.shell import git

_YAZAN_VEYA_CALISTIRAN = [
    "awk 'BEGIN {system(\"printf test\")}'",
    "awk '{print > \"cikti.txt\"}' girdi.txt",
    "awk '{print | \"sh\"}' girdi.txt",
    "awk '{\"date\" | getline d; print d}' girdi.txt",
    "awk -f betik.awk girdi.txt",
    "gawk -i inplace '{print}' girdi.txt",
    "sed 'w /tmp/fusion-research-test' input.txt",
    "sed -n '/x/w kopya.txt' input.txt",
    "sed 's/a/b/w kopya.txt' input.txt",
    "sed 's/.*/date/e' input.txt",
    "sed '1e date' input.txt",
    "sed -e 'p' -e 'w out.txt' input.txt",
    "sed -f betik.sed input.txt",
    "git branch -D example",
    "git branch -d example",
    "git branch -m eski yeni",
    "git branch yeni-dal",
    "git branch -u origin/main",
    "git tag -d v1",
    "git tag v1",
    "git remote add kotu https://evil.example/r.git",
    "git remote set-url origin https://evil.example/r.git",
]

_SALT_OKUR = [
    "awk '/hata/ {print $1}' log.txt",
    "awk '$3 > 100 {print $1}' veri.txt",
    "awk -F: '{print $1 || $2}' /dev/null",
    "awk 'NR==1' a.txt",
    "sed -n 1,5p a.py",
    "sed 's/hello world/bye/' a.txt",
    "sed -e 's/eski/yeni/g' a.txt",
    "sed -n '/where/p' a.txt",
    "git branch",
    "git branch -a",
    "git branch -vv",
    "git branch --show-current",
    "git branch --list 'feat/*'",
    "git branch --contains HEAD",
    "git tag",
    "git tag -l 'v*'",
    "git remote -v",
    "git remote show origin",
    "git remote get-url origin",
]


@pytest.mark.parametrize("komut", _YAZAN_VEYA_CALISTIRAN)
def test_yazan_veya_calistiran_komut_salt_okur_sayilmaz(komut):
    assert not is_read_only_command(komut)


@pytest.mark.parametrize("komut", _SALT_OKUR)
def test_mesru_okuma_salt_okur_kalir(komut):
    assert is_read_only_command(komut)


@pytest.mark.parametrize(
    "komut",
    [
        "awk 'BEGIN {system(\"rm -rf build\")}'",
        "sed 'w /tmp/x' input.txt",
        "git branch -D example",
        "git stash drop",
        "git stash clear",
        "npm run deploy",
        "pnpm run publish",
        "curl --json @example.json https://example.invalid",
        "curl -dveri=1 https://example.invalid",
    ],
)
def test_edits_kipi_gozetimsiz_calistirmaz(komut, tmp_path):
    assert not is_unattended_safe(komut, tmp_path)


@pytest.mark.parametrize(
    "komut",
    ["git stash", "git stash push -m not", "git stash list", "npm run test", "npm run build"],
)
def test_edits_kipi_yerel_isi_sormaz(komut, tmp_path):
    assert is_unattended_safe(komut, tmp_path)


def test_otomatik_kip_curl_json_gonderimini_sorar(tmp_path):
    assert auto_risk("curl --json @example.json https://example.invalid", tmp_path)


@pytest.mark.parametrize(
    "alt_komut", ["branch -D example", "branch -m a b", "tag -d v1", "remote add x https://e.x"]
)
def test_salt_okur_git_araci_degistirici_alt_komutu_reddeder(alt_komut, tmp_path):
    sonuc = git({"subcommand": alt_komut}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert "salt-okunur" in sonuc.output
