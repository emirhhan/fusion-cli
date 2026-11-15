"""`git restore .` ve eşdeğerleri kaydedilmemiş işi sormadan silemez (T1-04).

Ölçüldü (29 Ekim): `git restore .`, `git checkout .`, `git checkout HEAD -- .` için
danger_reason None ve is_unattended_safe True dönüyordu (`git checkout -- .` DANGER_RULES'taydı).
`git branch -D`, `git tag -d`, `git remote set-url`, `git stash drop` d80d6943 ile zaten kapalı.
"""

from __future__ import annotations

import pytest

from fusion_cli.tools.command_policy import is_unattended_safe
from fusion_cli.tools.safety import danger_reason

_TUM_AGACI_ATAN = [
    "git restore .",
    "git restore ./",
    "git restore :/",
    "git restore '*'",
    "git restore --worktree .",
    "git restore --source=HEAD~1 .",
    "git checkout .",
    "git checkout -- .",
    "git checkout HEAD -- .",
    "git checkout main .",
    "git -C app restore .",
    "git switch --discard-changes main",
]


@pytest.mark.parametrize("komut", _TUM_AGACI_ATAN)
def test_tum_agaci_atan_git_komutlari_sorulur(komut):
    assert is_unattended_safe(komut) is False, komut
    assert danger_reason("run_shell", {"command": komut}) is not None, komut


@pytest.mark.parametrize(
    "komut",
    [
        "git restore a.ts",
        "git restore src/app.ts src/b.ts",
        "git restore --staged .",
        "git restore --staged src",
        "git checkout -b ozellik",
        "git checkout main",
        "git checkout -- a.ts",
        "git switch main",
        "git stash",
        "git status",
        "git branch",
        "git branch -vv",
        "git tag -l",
        "git remote -v",
        "git diff --stat",
    ],
)
def test_mesru_git_isleri_sorulmaz(komut):
    assert is_unattended_safe(komut) is True, komut
    assert danger_reason("run_shell", {"command": komut}) is None, komut


@pytest.mark.parametrize(
    "komut",
    [
        "git branch -D ana",
        "git branch -m eski yeni",
        "git tag -d v1",
        "git remote set-url origin https://baska.example/x.git",
        "git remote add evil https://evil.example/x.git",
        "git stash drop",
        "git stash clear",
        "git diff --output=hedef.txt",
        "git log --output=hedef.txt",
    ],
)
def test_dal_etiket_uzak_yazanlar_sorulur(komut):
    """d80d6943'ten beri kapalı; gerileme koruması."""
    assert is_unattended_safe(komut) is False, komut
