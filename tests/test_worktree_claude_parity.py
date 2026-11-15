"""Claude Code çalışma ağacı birebirliği: konum (#337) ve adsız `-w` (#339)."""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import pytest

from fusion_cli.cli.worktree_argv import fill_missing_worktree_name
from fusion_cli.core import worktree as core_worktree
from fusion_cli.core.worktree_names import random_worktree_name


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "depo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fusion@test.local")
    _git(root, "config", "user.name", "Fusion Test")
    (root / "a.txt").write_text("taban\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "taban")
    return root


def test_agac_claude_worktrees_altinda_ve_git_disinda(repo):
    tree = core_worktree.enter_worktree(repo, "ozellik")
    assert tree.path == repo / ".claude" / "worktrees" / "ozellik"
    assert tree.branch == "worktree-ozellik"
    exclude = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert ".claude/worktrees/" in exclude and ".fusion/" in exclude
    assert _git(repo, "status", "--porcelain") == ""
    assert core_worktree.project_root_of(tree.path / "alt") == repo


def test_eski_fusion_worktrees_agaci_ilk_erisimde_tasinir(repo):
    legacy = repo / ".fusion" / "worktrees" / "eski"
    legacy.parent.mkdir(parents=True)
    _git(repo, "worktree", "add", "-q", "-b", "worktree-eski", str(legacy))
    (legacy / "is.txt").write_text("iş\n", encoding="utf-8")
    meta = repo / ".fusion" / "worktrees" / ".meta" / "eski.json"
    meta.parent.mkdir(parents=True)
    meta.write_text('{"branch": "worktree-eski", "base_commit": ""}', encoding="utf-8")

    tree = core_worktree.find_worktree(repo, "eski")

    assert tree is not None and tree.path == repo / ".claude" / "worktrees" / "eski"
    assert (tree.path / "is.txt").read_text(encoding="utf-8") == "iş\n"
    assert not legacy.exists()
    assert str(tree.path) in _git(repo, "worktree", "list")
    assert core_worktree.worktree_for_path(legacy.parent / "baska") is None


def test_eski_yoldaki_agacin_icinden_de_taninir(repo):
    legacy = repo / ".fusion" / "worktrees" / "x"
    assert core_worktree.project_root_of(legacy / "src") == repo


def test_rastgele_ad_claude_bicimi_ve_gecerli():
    ad = random_worktree_name(random.Random(1))
    assert len(ad.split("-")) == 3
    assert core_worktree.validate_name(ad) == ad


@pytest.mark.parametrize(
    ("argv", "beklenen"),
    [
        (["-w"], ["-w", "AD"]),
        (["--worktree"], ["--worktree", "AD"]),
        (["-w", "--name", "x"], ["-w", "AD", "--name", "x"]),
        (["agent", "-w", "-m", "auto", "görev"], ["agent", "-w", "AD", "-m", "auto", "görev"]),
        (["-w", "ozel"], ["-w", "ozel"]),
        (["--worktree=ozel"], ["--worktree=ozel"]),
        (["--", "-w"], ["--", "-w"]),
    ],
)
def test_adsiz_worktree_bayragina_ad_uretilir(argv, beklenen):
    assert fill_missing_worktree_name(argv, namer=lambda: "AD") == beklenen


@pytest.mark.parametrize(
    ("metin", "numara"),
    [
        ("#12", 12),
        ("https://github.com/o/r/pull/34", 34),
        ("https://github.com/o/r/pull/34/files", 34),
        ("https://gitlab.com/g/alt/r/-/merge_requests/5", 5),
    ],
)
def test_pr_mr_baglantisindan_yalniz_numara_okunur(metin, numara):
    from fusion_cli.core.worktree_pr import parse_pull_request

    ref = parse_pull_request(metin)
    assert ref is not None and ref.number == numara
    assert ref.worktree_name == f"pr-{numara}"
    assert parse_pull_request("ozellik") is None


@pytest.mark.parametrize(
    ("uzak", "beklenen"),
    [
        ("git@github.com:o/r.git", ("pull/3/head",)),
        ("https://github.com/o/r.git", ("pull/3/head",)),
        ("ssh://git@gitlab.com/g/r.git", ("merge-requests/3/head",)),
        ("https://git.sirket.local/g/r.git", ("pull/3/head", "merge-requests/3/head")),
    ],
)
def test_cekme_yolu_originin_sunucusuna_gore(uzak, beklenen):
    from fusion_cli.core.worktree_pr import PullRequestRef

    assert PullRequestRef(3).refspecs(uzak) == beklenen


def test_pr_numarasindan_agac_acilir(repo, tmp_path):
    """`--worktree "#7"`: origin'den pull/7/head çekilir, `.claude/worktrees/pr-7` açılır."""
    uzak = tmp_path / "uzak.git"
    _git(tmp_path, "clone", "-q", "--bare", str(repo), str(uzak))
    _git(repo, "checkout", "-q", "-b", "pr-dali")
    (repo / "pr.txt").write_text("pr işi\n", encoding="utf-8")
    _git(repo, "add", "pr.txt")
    _git(repo, "commit", "-qm", "pr")
    _git(repo, "push", "-q", str(uzak), "HEAD:refs/pull/7/head")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "branch", "-q", "-D", "pr-dali")
    _git(repo, "remote", "add", "origin", str(uzak))

    tree = core_worktree.enter_worktree(repo, "#7")

    assert tree.name == "pr-7"
    assert tree.path == repo / ".claude" / "worktrees" / "pr-7"
    assert (tree.path / "pr.txt").read_text(encoding="utf-8") == "pr işi\n"
    assert core_worktree.enter_worktree(repo, "#7").path == tree.path  # ikinci kez aynı ağaç


def test_pr_cekilemezse_claude_mesaji(repo, tmp_path):
    from fusion_cli.core.errors import WorktreeError

    uzak = tmp_path / "bos.git"
    _git(tmp_path, "init", "-q", "--bare", str(uzak))
    _git(repo, "remote", "add", "origin", str(uzak))
    with pytest.raises(WorktreeError, match="PR/MR #9 çekilemedi"):
        core_worktree.enter_worktree(repo, "#9")


def _uzakli_depo(repo: Path, tmp_path: Path) -> Path:
    """`origin` (varsayılan dal ana) + yerelde ilerlemiş, push edilmemiş commit."""
    uzak = tmp_path / "uzak.git"
    _git(tmp_path, "clone", "-q", "--bare", str(repo), str(uzak))
    _git(repo, "remote", "add", "origin", str(uzak))
    _git(repo, "fetch", "-q", "origin")
    _git(repo, "remote", "set-head", "origin", "--auto")
    (repo / "yerel.txt").write_text("push edilmedi\n", encoding="utf-8")
    _git(repo, "add", "yerel.txt")
    _git(repo, "commit", "-qm", "yerel")
    return uzak


def test_fresh_taban_uzak_varsayilan_daldan_dallanir(repo, tmp_path):
    _uzakli_depo(repo, tmp_path)
    tree = core_worktree.enter_worktree(repo, "taze", base_mode="fresh")
    assert not (tree.path / "yerel.txt").exists()
    assert tree.base_commit == _git(repo, "rev-parse", "origin/HEAD")


def test_head_taban_yerel_isi_tasir(repo, tmp_path):
    _uzakli_depo(repo, tmp_path)
    tree = core_worktree.enter_worktree(repo, "yerel", base_mode="head")
    assert (tree.path / "yerel.txt").exists()


def test_fresh_taban_uzak_yoksa_yerel_heade_duser(repo):
    tree = core_worktree.enter_worktree(repo, "uzaksiz", base_mode="fresh")
    assert tree.base_commit == _git(repo, "rev-parse", "HEAD")


def test_fresh_taban_24_saatten_eski_depoyu_ceker(repo, tmp_path, monkeypatch):
    from fusion_cli.core import worktree_fetch

    _uzakli_depo(repo, tmp_path)
    cagrilar: list[tuple[str, ...]] = []
    gercek = worktree_fetch.quiet_git

    def _izle(cwd, args, *, timeout_s, network=False):
        cagrilar.append(tuple(args))
        return gercek(cwd, args, timeout_s=timeout_s, network=network)

    monkeypatch.setattr(worktree_fetch, "quiet_git", _izle)
    worktree_fetch.fresh_base(repo, now=10**12)
    assert ("fetch", "--quiet", "origin", "main") in cagrilar or (
        "fetch",
        "--quiet",
        "origin",
        "master",
    ) in cagrilar
    cagrilar.clear()
    worktree_fetch.fresh_base(repo)
    assert not any(c[0] == "fetch" for c in cagrilar), "yeni çekilmiş depo yeniden çekildi"


def test_sessiz_git_ortami_soru_acmaz():
    from fusion_cli.core.worktree_fetch import quiet_env

    env = quiet_env({"PATH": "/bin"})
    assert env["GIT_TERMINAL_PROMPT"] == "0" and "BatchMode=yes" in env["GIT_SSH_COMMAND"]


def test_baseref_ayari_claude_settings_jsondan_okunur(repo, tmp_path, monkeypatch):
    from fusion_cli.config import worktree_settings

    home = tmp_path / "ev"
    (home / ".claude").mkdir(parents=True)
    assert worktree_settings.worktree_base_mode(repo, home=home) == "fresh"
    (home / ".claude" / "settings.json").write_text(
        '{"worktree": {"baseRef": "head"}}', encoding="utf-8"
    )
    assert worktree_settings.worktree_base_mode(repo, home=home) == "head"
    (home / ".claude" / "settings.json").write_text(
        '{"worktree": {"baseRef": "main"}}', encoding="utf-8"
    )
    assert worktree_settings.worktree_base_mode(repo, home=home) == "fresh"


def test_ayarli_giris_varsayilan_fresh_tabani_kullanir(repo, tmp_path, monkeypatch):
    from fusion_cli.config import worktree_settings

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "ev" / ".claude"))
    _uzakli_depo(repo, tmp_path)
    tree = worktree_settings.enter_configured_worktree(repo, "ayarli")
    assert not (tree.path / "yerel.txt").exists()


def test_fresh_yedegi_agac_icinde_o_agacin_headi(repo):
    ilk = core_worktree.enter_worktree(repo, "ilk", base_mode="head")
    (ilk.path / "dal.txt").write_text("dal işi\n", encoding="utf-8")
    _git(ilk.path, "add", "dal.txt")
    _git(ilk.path, "commit", "-qm", "dal")
    ikinci = core_worktree.enter_worktree(ilk.path, "ikinci", base_mode="fresh")
    assert (ikinci.path / "dal.txt").exists()


def _uzagi_ilerlet(uzak: Path, tmp_path: Path) -> str:
    klon = tmp_path / "klon"
    _git(tmp_path, "clone", "-q", str(uzak), str(klon))
    _git(klon, "config", "user.email", "fusion@test.local")
    _git(klon, "config", "user.name", "Fusion Test")
    (klon / "yeni.txt").write_text("uzakta yeni\n", encoding="utf-8")
    _git(klon, "add", "yeni.txt")
    _git(klon, "commit", "-qm", "uzak ilerledi")
    _git(klon, "push", "-q")
    return _git(klon, "rev-parse", "HEAD")


def test_temiz_ve_commitsiz_agac_yeniden_acilinca_varsayilan_dala_gelir(repo, tmp_path):
    """Claude Code 'Reuse a worktree name' (#373)."""
    uzak = _uzakli_depo(repo, tmp_path)
    tree = core_worktree.enter_worktree(repo, "tekrar", base_mode="fresh")
    yeni = _uzagi_ilerlet(uzak, tmp_path)
    _git(repo, "fetch", "-q", "origin")
    again = core_worktree.enter_worktree(repo, "tekrar", base_mode="fresh")
    assert again.path == tree.path
    assert _git(tree.path, "rev-parse", "HEAD") == yeni


def test_isi_olan_agac_eski_ucunda_acilir(repo, tmp_path):
    uzak = _uzakli_depo(repo, tmp_path)
    tree = core_worktree.enter_worktree(repo, "isli", base_mode="fresh")
    (tree.path / "kendi.txt").write_text("iş\n", encoding="utf-8")
    _git(tree.path, "add", "kendi.txt")
    _git(tree.path, "commit", "-qm", "kendi")
    uc = _git(tree.path, "rev-parse", "HEAD")
    _uzagi_ilerlet(uzak, tmp_path)
    _git(repo, "fetch", "-q", "origin")
    core_worktree.enter_worktree(repo, "isli", base_mode="fresh")
    assert _git(tree.path, "rev-parse", "HEAD") == uc
    (tree.path / "kirli.txt").write_text("x", encoding="utf-8")
    core_worktree.enter_worktree(repo, "isli", base_mode="head")
    assert _git(tree.path, "rev-parse", "HEAD") == uc


def test_sessiz_git_kullanicinin_core_sshcommand_ayarini_ezmez(repo, monkeypatch):
    """Ortamdaki GIT_SSH_COMMAND core.sshCommand'ı ezerdi: kullanıcının anahtarı kaybolurdu
    (bağımsız inceleme #4). Ayar varsa ona BatchMode eklenir, ortam değişkeni konmaz."""
    from fusion_cli.core import worktree_fetch

    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    _git(repo, "config", "core.sshCommand", "ssh -i /anahtar/is")
    yakalanan: list[tuple[list[str], dict[str, str]]] = []
    gercek = subprocess.run

    def _kaydet(args, **kwargs):
        if args[:2] == ["git", "-c"] or "fetch" in args:
            yakalanan.append((list(args), dict(kwargs["env"])))
        return gercek(args, **kwargs)

    monkeypatch.setattr(worktree_fetch.subprocess, "run", _kaydet)
    worktree_fetch.quiet_git(repo, ("fetch", "--quiet", "origin"), timeout_s=5, network=True)
    args, env = yakalanan[-1]
    assert "GIT_SSH_COMMAND" not in env
    assert "core.sshCommand=ssh -i /anahtar/is -o BatchMode=yes" in args


def test_sessiz_git_ayar_yoksa_batchmode_ortamdan(repo, monkeypatch):
    from fusion_cli.core import worktree_fetch

    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    yakalanan: list[dict[str, str]] = []
    gercek = subprocess.run

    def _kaydet(args, **kwargs):
        if "fetch" in args:
            yakalanan.append(dict(kwargs["env"]))
        return gercek(args, **kwargs)

    monkeypatch.setattr(worktree_fetch.subprocess, "run", _kaydet)
    worktree_fetch.quiet_git(repo, ("fetch", "--quiet", "origin"), timeout_s=5, network=True)
    assert "BatchMode=yes" in yakalanan[-1]["GIT_SSH_COMMAND"]


def test_pr_cekme_hatasi_git_nedenini_soyler(repo):
    from fusion_cli.core.errors import WorktreeError
    from fusion_cli.core.worktree_fetch import fetch_pull_request

    with pytest.raises(WorktreeError) as hata:
        fetch_pull_request(repo, ("pull/7/head",), 7)
    assert "#7" in str(hata.value) and "origin" in str(hata.value)
