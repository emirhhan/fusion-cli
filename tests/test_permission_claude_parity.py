"""İzin kuralı eşlemesinin Claude Code belgesiyle birebirliği (izinler alanı).

Kaynak: https://code.claude.com/docs/en/permissions (wildcard-patterns, tool-name-wildcards,
read-and-edit, how-path-patterns-match, symlinks, webfetch, match-by-input-parameter).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.config.permission_rules import (
    LAYER_PROJECT,
    LAYER_USER,
    PermissionDecision,
    PermissionRule,
    PermissionRuleSet,
    parse_rule,
)
from fusion_cli.tools.permission_match import evaluate

ALLOW = PermissionDecision.ALLOW
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


def _kume(*ciftler: tuple[str, str], source: str = "test") -> PermissionRuleSet:
    kurallar: list[PermissionRule] = []
    for metin, karar in ciftler:
        kural = parse_rule(metin, PermissionDecision(karar), source=source)
        assert kural is not None, metin
        kurallar.append(kural)
    return PermissionRuleSet(rules=tuple(kurallar))


def _karar(kume, arac, args, kok):
    sonuc = evaluate(kume, arac, args, kok)
    return None if sonuc is None else sonuc.decision


# --- #43 Bash `*` konumu ---------------------------------------------------- #


@pytest.mark.parametrize(
    ("kural", "komut", "beklenen"),
    [
        ("git * main", "git push origin main", True),
        ("git * main", "git log", False),
        ("git log * main", "git log main", False),
        ("* --version", "node --version", True),
        ("* --version", "node -v", False),
        ("ls *", "ls", True),
        ("ls *", "lsof", False),
        ("ls*", "lsof", True),
        ("* --help *", "npm --help x", True),
        ("* --help *", "npm --help", False),
        ("ls:*", "ls -la", True),
        ("git:* push", "git x push", False),
        ("npm run build", "npm run build --watch", False),
    ],
)
def test_bash_yildizi_her_konumda(tmp_path, kural, komut, beklenen):
    kume = _kume((f"Bash({kural})", "allow"))
    assert (_karar(kume, "run_shell", {"command": komut}, tmp_path) is ALLOW) is beklenen


# --- #46 araç adı globu ----------------------------------------------------- #


def test_arac_adi_globu_deny_ve_ask_tam_ad(tmp_path):
    assert _karar(_kume(("*", "deny")), "read_file", {"path": "a"}, tmp_path) is DENY
    kume = _kume(("mcp__*", "ask"))
    assert _karar(kume, "meta__ads_list", {}, tmp_path) is ASK
    assert _karar(kume, "read_file", {"path": "a"}, tmp_path) is None


def test_arac_adi_globu_allow_sabit_sunucu_oneki_ister(tmp_path):
    for kalip in ("*", "B*", "mcp__*"):
        assert _karar(_kume((kalip, "allow")), "meta__ads_list", {}, tmp_path) is None
    kume = _kume(("mcp__meta__ads_*", "allow"))
    assert _karar(kume, "meta__ads_list", {}, tmp_path) is ALLOW
    assert _karar(kume, "meta__campaign_list", {}, tmp_path) is None


# --- #62 WebFetch alan adı -------------------------------------------------- #


@pytest.mark.parametrize(
    ("kalip", "url", "beklenen"),
    [
        ("example.com", "https://example.com/x", True),
        ("example.com", "https://api.example.com/x", False),
        ("*.example.com", "https://a.b.example.com/", True),
        ("*.example.com", "https://example.com/", False),
        ("*", "https://herhangi.org/", True),
        ("example.*", "https://example.org/", True),
        ("example.*", "https://example.evil.com/", False),
        ("EXAMPLE.com.", "https://example.com./", True),
    ],
)
def test_webfetch_alan_adi_birebir(tmp_path, kalip, url, beklenen):
    kume = _kume((f"WebFetch(domain:{kalip})", "deny"))
    assert (_karar(kume, "web_fetch", {"url": url}, tmp_path) is DENY) is beklenen


# --- #45 dayanak ve derinlik ------------------------------------------------ #


def test_yalin_dosya_adi_her_derinlikte(tmp_path):
    kume = _kume(("Read(.env)", "deny"))
    assert _karar(kume, "read_file", {"path": "sub/dir/.env"}, tmp_path) is DENY
    assert _karar(kume, "read_file", {"path": ".env"}, tmp_path) is DENY
    assert _karar(kume, "read_file", {"path": str(tmp_path.parent / ".env")}, tmp_path) is None


def test_tek_bolumlu_dizin_deny_derine_allow_koke(tmp_path):
    hedef = {"path": "vendor/pkg/src/lib.js"}
    assert _karar(_kume(("Edit(src/**)", "deny")), "edit_file", hedef, tmp_path) is DENY
    assert _karar(_kume(("Edit(src/**)", "allow")), "edit_file", hedef, tmp_path) is None
    assert _karar(_kume(("Edit(/src/**)", "deny")), "edit_file", hedef, tmp_path) is None
    assert (
        _karar(_kume(("Edit(src/**)", "allow")), "edit_file", {"path": "src/a.ts"}, tmp_path)
        is ALLOW
    )


def test_kullanici_ayarindaki_tek_egik_cizgi_claude_dizinine_baglanir(tmp_path, _izole_ev):
    kume = _kume(("Read(/secrets/**)", "deny"), source=LAYER_USER)
    assert _karar(kume, "read_file", {"path": "secrets/a"}, tmp_path) is None
    yol = str(_izole_ev / ".claude" / "secrets" / "a")
    assert _karar(kume, "read_file", {"path": yol}, tmp_path) is DENY
    proje = _kume(("Read(/secrets/**)", "deny"), source=LAYER_PROJECT)
    assert _karar(proje, "read_file", {"path": "secrets/a"}, tmp_path) is DENY


# --- #61 symlink ------------------------------------------------------------ #


def test_symlink_allow_iki_yolu_da_ister_deny_birini(tmp_path, _izole_ev):
    dis = _izole_ev / ".ssh"
    dis.mkdir()
    (dis / "id_rsa").write_text("x")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "anahtar").symlink_to(dis / "id_rsa")
    allow = _kume(("Read(./**)", "allow"))
    assert _karar(allow, "read_file", {"path": "anahtar"}, proje) is None
    deny = _kume(("Read(~/.ssh/**)", "deny"))
    assert _karar(deny, "read_file", {"path": "anahtar"}, proje) is DENY


# --- #60 Read deny yazmayı da engeller -------------------------------------- #


def test_read_deny_edit_ve_write_i_engeller(tmp_path):
    kume = _kume(("Read(./gizli/**)", "deny"))
    for arac in ("write_file", "edit_file"):
        assert _karar(kume, arac, {"path": "gizli/yeni.txt"}, tmp_path) is DENY
    ask = _kume(("Read(./gizli/**)", "ask"))
    assert _karar(ask, "write_file", {"path": "gizli/yeni.txt"}, tmp_path) is None


# --- #78 Write/Glob/MultiEdit/NotebookEdit yol kuralı eşleşmez -------------- #


@pytest.mark.parametrize("arac_kurali", ["Write", "MultiEdit", "NotebookEdit", "Glob"])
def test_yol_belirtecli_write_glob_kurali_eslesmez(tmp_path, arac_kurali):
    kume = _kume((f"{arac_kurali}(docs/**)", "deny"))
    for arac, args in (("write_file", {"path": "docs/a"}), ("glob", {"path": "docs"})):
        assert _karar(kume, arac, args, tmp_path) is None
    assert _karar(_kume(("Write", "deny")), "write_file", {"path": "docs/a"}, tmp_path) is DENY


# --- #79 `!` olumsuzlama ---------------------------------------------------- #


def test_olumsuzlama_ayni_kaynakta_onceki_kurali_oyar(tmp_path):
    kume = _kume(("Read(*.env)", "deny"), ("Read(!sample.env)", "deny"))
    assert _karar(kume, "read_file", {"path": "a/prod.env"}, tmp_path) is DENY
    assert _karar(kume, "read_file", {"path": "a/sample.env"}, tmp_path) is None


def test_olumsuzlama_sinirlari(tmp_path):
    once = _kume(("Read(!sample.env)", "deny"), ("Read(*.env)", "deny"))
    assert _karar(once, "read_file", {"path": "sample.env"}, tmp_path) is DENY
    dizin = _kume(("Read(secrets/**)", "deny"), ("Read(!secrets/public/**)", "deny"))
    assert _karar(dizin, "read_file", {"path": "secrets/public/a"}, tmp_path) is DENY
    baska = PermissionRuleSet(
        rules=(
            parse_rule("Read(*.env)", DENY, source="yonetilen"),
            parse_rule("Read(!sample.env)", DENY, source="proje"),
        )
    )
    assert _karar(baska, "read_file", {"path": "sample.env"}, tmp_path) is DENY


# --- #80 parametre kuralı --------------------------------------------------- #


def test_parametre_kurali_deny_ve_ask(tmp_path):
    kume = _kume(("Bash(run_in_background:true)", "deny"))
    args = {"command": "npm run dev", "run_in_background": True}
    assert _karar(kume, "run_shell", args, tmp_path) is DENY
    assert _karar(kume, "run_shell", {"command": "npm run dev"}, tmp_path) is None
    ajan = _kume(("Agent(model : opus)", "ask"), ("Agent(isolation:*)", "deny"))
    assert _karar(ajan, "spawn_agent", {"uzman": "x", "model": "opus"}, tmp_path) is ASK
    assert _karar(ajan, "spawn_agent", {"uzman": "x", "model": "claude-opus-4"}, tmp_path) is None
    assert _karar(ajan, "spawn_agent", {"uzman": "x", "isolation": "worktree"}, tmp_path) is DENY


def test_parametre_kurali_birincil_alanda_ve_allowda_yok(tmp_path):
    assert (
        _karar(_kume(("Bash(command:rm *)", "deny")), "run_shell", {"command": "rm x"}, tmp_path)
        is None
    )
    allow = _kume(("Agent(model:opus)", "allow"))
    assert _karar(allow, "spawn_agent", {"uzman": "x", "model": "opus"}, tmp_path) is None


# --- #44, #59 Read/Edit kuralları kabukta ----------------------------------- #


def test_read_deny_kabuk_dosya_komutlarina_uygulanir(tmp_path, _izole_ev):
    kume = _kume(("Read(~/.ssh/**)", "deny"))
    for komut in ("cat ~/.ssh/id_rsa", "head -n 5 ~/.ssh/id_rsa", "wc < ~/.ssh/id_rsa"):
        assert _karar(kume, "run_shell", {"command": komut}, tmp_path) is DENY, komut
    assert _karar(kume, "run_shell", {"command": "grep -r x ."}, tmp_path) is None


def test_edit_kurali_yonlendirme_ve_tee_hedefini_denetler(tmp_path):
    kume = _kume(("Edit(./kilitli/**)", "deny"), ("Bash(echo *)", "allow"))
    for komut in ("echo x > kilitli/a", "echo x >> kilitli/a", "echo x | tee kilitli/a"):
        assert _karar(kume, "run_shell", {"command": komut}, tmp_path) is DENY, komut
    # Bash allow komutu onaylar, hedefi değil; Edit allow hedefi açar.
    assert _karar(kume, "run_shell", {"command": "echo x > cikti.txt"}, tmp_path) is None
    acik = _kume(("Edit(./cikti/**)", "allow"), ("Bash(echo *)", "allow"))
    assert _karar(acik, "run_shell", {"command": "echo x > cikti/a.txt"}, tmp_path) is ALLOW
    assert _karar(acik, "run_shell", {"command": "echo x > ~/a.txt"}, tmp_path) is None
