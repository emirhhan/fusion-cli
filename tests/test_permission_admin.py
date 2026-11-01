"""İzin kuralı yönetimi üç yüzeyde (P-003): `/permissions`, `fusion permissions`, `izin.*` RPC;
proje güveni masaüstünde (P-012): `proje.guven_durum/guven_ver/guven_kaldir`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.permissions_command import permissions
from fusion_cli.config import trust
from fusion_cli.config.permission_rules import user_permissions_file
from fusion_cli.config.trust import PROJECT_PERMISSIONS_PATH

from .fakes import make_config


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    return ev


@pytest.fixture
def proje(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


def _state(proje):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    return ReplState(config=make_config(), memory=null_memory(), root=proje, home=proje / "ev")


def _oku(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- REPL --------------------------------------------------------------------- #


def test_permissions_komutu_kayitli_ve_izinler_takma_adi(proje):
    registry = build_registry()
    assert registry.get("permissions") is registry.get("izinler")


def test_repl_ekle_listele_sil(proje):
    state = _state(proje)
    assert "yok" in permissions(state, "").lower()
    sonuc = permissions(state, "add allow Bash(npm test *)")
    assert "eklendi" in sonuc and "Bash(npm test *)" in sonuc
    # Proje henüz güvenilmiyordu ama izin dosyası yoktu: Fusion yazdı, karmayı kaydetti.
    hedef = proje / PROJECT_PERMISSIONS_PATH
    assert _oku(hedef)["permissions"]["allow"] == ["Bash(npm test *)"]
    assert trust.is_permissions_trusted(proje)
    assert "zaten var" in permissions(state, "add allow Bash(npm test *)")
    liste = permissions(state, "list")
    assert "Bash(npm test *)" in liste and "[allow]" in liste and "(yerel)" in liste
    assert "silindi" in permissions(state, "remove allow Bash(npm test *)")
    assert _oku(hedef)["permissions"]["allow"] == []
    assert "bulunamadı" in permissions(state, "remove allow Bash(npm test *)")


def test_repl_user_bayragi_kullanici_dosyasina_yazar_ve_hatalar_turkce(proje):
    state = _state(proje)
    sonuc = permissions(state, "add deny Read(~/.ssh/**) --user")
    assert str(user_permissions_file()) in sonuc
    assert _oku(user_permissions_file())["permissions"]["deny"] == ["Read(~/.ssh/**)"]
    assert "allow, ask ya da deny" in permissions(state, "add belki Bash(ls)")
    assert "biçiminde" in permissions(state, "add allow Bash(")
    assert "Kullanım" in permissions(state, "bilinmeyen")


# --- CLI ----------------------------------------------------------------------- #


def test_fusion_permissions_cli(proje):
    from fusion_cli.cli.app import app

    runner = CliRunner()
    sonuc = runner.invoke(
        app, ["permissions", "add", "deny", "Bash(git push *)", "--path", str(proje)]
    )
    assert sonuc.exit_code == 0, sonuc.output
    assert "Bash(git push *)" in sonuc.output
    sonuc = runner.invoke(app, ["permissions", "list", "--path", str(proje)])
    assert sonuc.exit_code == 0 and "[deny]" in sonuc.output
    sonuc = runner.invoke(app, ["permissions", "add", "belki", "Bash(ls)", "--path", str(proje)])
    assert sonuc.exit_code == 2


# --- RPC ------------------------------------------------------------------------- #


async def _rpc(session, lines, name, data=None):
    await session.handle(Request(id=name, name=name, data=data or {}))
    return json.loads(lines[-1])["veri"]


async def test_izin_rpc_ekle_listele_sil_ve_engel(proje):
    lines: list[str] = []
    session = AppSession(lines.append, root=proje, home=proje / "ev")
    try:
        eklendi = await _rpc(
            session, lines, "izin.ekle", {"kalip": "Edit(/src/**)", "karar": "allow"}
        )
        assert eklendi["ok"] is True
        tablo = await _rpc(session, lines, "izin.kurallar")
        satirlar = [(k["kalip"], k["karar"], k["kaynak"]) for k in tablo["kurallar"]]
        assert ("Edit(/src/**)", "allow", "yerel") in satirlar
        assert tablo["hedef"].endswith("settings.local.json")
        assert tablo["kok_disi_yazma_engeli"] is False
        kotu = await _rpc(session, lines, "izin.ekle", {"kalip": "Bash(", "karar": "allow"})
        assert kotu["ok"] is False
        silindi = await _rpc(
            session, lines, "izin.sil", {"kalip": "Edit(/src/**)", "karar": "allow"}
        )
        assert silindi["ok"] is True
        yok = await _rpc(session, lines, "izin.sil", {"kalip": "Edit(/src/**)", "karar": "allow"})
        assert yok["ok"] is False
        engel = await _rpc(
            session, lines, "izin.engel", {"anahtar": "block_writes_outside_root", "deger": True}
        )
        assert engel == {"ok": True, "anahtar": "block_writes_outside_root", "deger": True}
        assert session._state.config.runtime.block_writes_outside_root is True
        durum = await _rpc(session, lines, "kontrol.durum")
        assert durum["izin"]["kok_disi_yazma_engeli"] is True
        assert durum["izin"]["guven"]["guvenildi"] is False
        bozuk = await _rpc(
            session, lines, "izin.engel", {"anahtar": "restrict_to_root", "deger": True}
        )
        assert bozuk["ok"] is False
    finally:
        await session.close()


async def test_proje_guven_rpc_dusurulen_bolumleri_soyler_ve_guven_verir(proje):
    (proje / "config.yaml").write_text(
        "mcp_servers:\n  - name: kotu\n    command: /bin/sh\n"
        "runtime:\n  verification_commands: ['x']\n",
        encoding="utf-8",
    )
    (proje / ".claude").mkdir()
    (proje / PROJECT_PERMISSIONS_PATH).write_text('{"permissions":{"allow":["Bash(*)"]}}')
    (proje / ".fusion" / "tools").mkdir(parents=True)
    (proje / ".fusion" / "tools" / "a.py").write_text("def run(a): return 1\n")
    lines: list[str] = []
    session = AppSession(lines.append, root=proje, home=proje / "ev")
    try:
        durum = await _rpc(session, lines, "proje.guven_durum")
        assert durum["guvenildi"] is False
        assert durum["neden"] == trust.REASON_UNKNOWN
        assert set(durum["dusurulen_bolumler"]) == {"mcp_servers", "runtime.verification_commands"}
        assert durum["yok_sayilan_dosyalar"] == [".claude/settings.local.json"]
        assert durum["yuklenmeyen_araclar"] == 1
        verildi = await _rpc(session, lines, "proje.guven_ver")
        assert verildi["guvenildi"] is True and verildi["dusurulen_bolumler"] == []
        assert session._state.allowed_commands == {"*"}
        kaldirildi = await _rpc(session, lines, "proje.guven_kaldir")
        assert kaldirildi["guvenildi"] is False
        assert session._state.allowed_commands == frozenset()
    finally:
        await session.close()


# --- remove_permission_rule: katmanlar ve güven ------------------------------------ #


def _yaz(path: Path, veri: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(veri), encoding="utf-8")


def test_sil_guvenilmeyen_yerel_dosyadan_reddedilir_ve_izin_acmaz(proje):
    """Ölçüldü (31 Ekim): güven kontrolü silmeden SONRA ve config güvenine bakıyordu; çekilen
    bir `Bash(*)` taşıyan güvenilmeyen dosyadan masum bir satır silinince karma tazeleniyor
    ve `Bash(*)` allow aktif oluyordu."""
    from fusion_cli.config import permission_admin
    from fusion_cli.config.permission_rules import format_rule, load_permission_rules
    from fusion_cli.core.errors import ConfigError

    # Klasöre hiç güvenilmedi (#67: güven klasöre bağlı; içerik karmasına değil).
    yerel = proje / PROJECT_PERMISSIONS_PATH
    _yaz(yerel, {"permissions": {"allow": ["Bash(*)", "Bash(ls *)"]}})
    assert not trust.is_permissions_trusted(proje)
    kural = permission_admin.parse_pattern("Bash(ls *)", permission_admin.parse_decision("allow"))
    with pytest.raises(ConfigError, match="güvenilmiyor"):
        permission_admin.remove_permission_rule(proje, kural)
    assert _oku(yerel)["permissions"]["allow"] == ["Bash(*)", "Bash(ls *)"]
    assert not trust.is_permissions_trusted(proje)
    yuklenen = load_permission_rules(proje)
    assert "Bash(*)" not in {format_rule(k) for k in yuklenen.rules}


def test_sil_fusionun_yazdigi_yerel_dosyada_karmayi_tazeler_kalan_kurallar_dusmez(proje):
    """Proje hiç `fusion trust` edilmemiş (sentinel kayıt); Fusion'ın yazdığı dosyadan silince
    kalan deny kuralı güvenilir kalmalı. Ölçüldü (31 Ekim): karma tazelenmiyor, dosya bütünüyle
    (deny dahil) düşüyordu."""
    from fusion_cli.config import permission_admin
    from fusion_cli.config.permission_rules import format_rule, load_permission_rules

    izin = permission_admin.parse_pattern("Bash(ls *)", permission_admin.parse_decision("allow"))
    yasak = permission_admin.parse_pattern("Bash(rm *)", permission_admin.parse_decision("deny"))
    permission_admin.add_permission_rule(proje, izin)
    permission_admin.add_permission_rule(proje, yasak)
    assert not trust.resolve_project_trust(proje).trusted
    silindi = permission_admin.remove_permission_rule(proje, izin)
    assert silindi is not None and silindi.path == proje / PROJECT_PERMISSIONS_PATH
    assert trust.is_permissions_trusted(proje)
    yuklenen = load_permission_rules(proje)
    assert {format_rule(k) for k in yuklenen.rules} == {"Bash(rm *)"}
    assert yuklenen.untrusted_layers == ()


def test_sil_salt_okunur_katmanlardan_reddedilir(proje, _izole_ev):
    """`~/.claude/settings.json` ve proje `.claude/settings.json` Fusion tarafından YAZILMAZ."""
    from fusion_cli.config import permission_admin
    from fusion_cli.config.permission_rules import rule_layers
    from fusion_cli.core.errors import ConfigError

    katmanlar = {k.name: k for k in rule_layers(proje)}
    _yaz(katmanlar["kullanici"].path, {"permissions": {"deny": ["Bash(rm *)"]}})
    _yaz(katmanlar["proje"].path, {"permissions": {"deny": ["Read(.env)", "Bash(rm *)"]}})
    trust.trust_project(proje)
    kural = permission_admin.parse_pattern("Bash(rm *)", permission_admin.parse_decision("deny"))
    with pytest.raises(ConfigError, match="salt okunur"):
        permission_admin.remove_permission_rule(proje, kural)
    assert _oku(katmanlar["kullanici"].path)["permissions"]["deny"] == ["Bash(rm *)"]
    assert _oku(katmanlar["proje"].path)["permissions"]["deny"] == ["Read(.env)", "Bash(rm *)"]
    assert trust.is_project_settings_trusted(proje)


def test_sil_dosya_verilirse_yalniz_o_katmandan_siler(proje):
    from fusion_cli.config import permission_admin

    kural = permission_admin.parse_pattern("Bash(ls *)", permission_admin.parse_decision("allow"))
    permission_admin.add_permission_rule(proje, kural, user_level=True)
    permission_admin.add_permission_rule(proje, kural)
    yerel = proje / PROJECT_PERMISSIONS_PATH
    silindi = permission_admin.remove_permission_rule(proje, kural, path=yerel)
    assert silindi is not None and silindi.path == yerel
    assert _oku(yerel)["permissions"]["allow"] == []
    assert _oku(user_permissions_file())["permissions"]["allow"] == ["Bash(ls *)"]
    # Satır tablosu hangi satırın silinebildiğini söyler.
    satirlar = permission_admin.rules_payload(proje, make_config())["kurallar"]
    assert all(s["silinebilir"] is True for s in satirlar)


async def test_izin_rpc_sil_dosya_ile_ve_salt_okunur_katman_turkce_hata(proje, _izole_ev):
    from fusion_cli.config.permission_rules import rule_layers

    katmanlar = {k.name: k for k in rule_layers(proje)}
    _yaz(katmanlar["kullanici"].path, {"permissions": {"deny": ["Bash(rm *)"]}})
    lines: list[str] = []
    session = AppSession(lines.append, root=proje, home=proje / "ev")
    try:
        await _rpc(session, lines, "izin.ekle", {"kalip": "Bash(rm *)", "karar": "deny"})
        tablo = await _rpc(session, lines, "izin.kurallar")
        satirlar = {k["kaynak"]: k for k in tablo["kurallar"]}
        assert satirlar["kullanici"]["silinebilir"] is False
        assert satirlar["yerel"]["silinebilir"] is True
        ret = await _rpc(
            session,
            lines,
            "izin.sil",
            {"kalip": "Bash(rm *)", "karar": "deny", "dosya": satirlar["kullanici"]["dosya"]},
        )
        assert ret["ok"] is False and "salt okunur" in ret["metin"]
        silindi = await _rpc(
            session,
            lines,
            "izin.sil",
            {"kalip": "Bash(rm *)", "karar": "deny", "dosya": satirlar["yerel"]["dosya"]},
        )
        assert silindi["ok"] is True and silindi["dosya"] == satirlar["yerel"]["dosya"]
        assert _oku(katmanlar["kullanici"].path)["permissions"]["deny"] == ["Bash(rm *)"]
    finally:
        await session.close()


# --- Kapsam: proje dosyası güvenilmiyorken kullanıcı dosyasına düşme ---------------- #


def _guvenilmeyen_yerel(proje: Path) -> None:
    _yaz(proje / PROJECT_PERMISSIONS_PATH, {"permissions": {"allow": ["Bash(*)"]}})
    assert not trust.is_permissions_trusted(proje)


def test_repl_ekle_kullanici_dosyasina_dusunce_tum_projeler_der(proje):
    """Ölçüldü (31 Ekim): 'projeye yaz' varsayılanı güvenilmeyen projede sessizce tüm projeleri
    etkileyen kullanıcı dosyasına yazıyordu; çıktı yalnız yolu gösteriyordu."""
    _guvenilmeyen_yerel(proje)
    sonuc = permissions(_state(proje), "add allow Bash(npm test *)")
    assert "eklendi" in sonuc and str(user_permissions_file()) in sonuc
    assert "tüm projeler" in sonuc.lower()
    # Açıkça --user istenirse not gerekmez.
    sonuc = permissions(_state(proje), "add allow Bash(pytest *) --user")
    assert "tüm projeler" not in sonuc.lower()


async def test_izin_rpc_ekle_proje_kapsami_guvenilmeyen_projede_reddedilir(proje):
    _guvenilmeyen_yerel(proje)
    lines: list[str] = []
    session = AppSession(lines.append, root=proje, home=proje / "ev")
    try:
        ret = await _rpc(
            session,
            lines,
            "izin.ekle",
            {"kalip": "Bash(npm test *)", "karar": "allow", "kapsam": "proje"},
        )
        assert ret["ok"] is False and "güvenilmiyor" in ret["metin"]
        assert not user_permissions_file().is_file()
        tamam = await _rpc(
            session,
            lines,
            "izin.ekle",
            {"kalip": "Bash(npm test *)", "karar": "allow", "kapsam": "kullanici"},
        )
        assert tamam["ok"] is True and tamam["dosya"] == str(user_permissions_file())
    finally:
        await session.close()


def test_allowed_tools_permissions_takma_adidir():
    """Claude (#83): `/allowed-tools` `/permissions`'ın takma adıdır."""
    from fusion_cli.cli.repl.commands import build_registry

    kayit = build_registry()
    assert kayit.get("allowed-tools") is kayit.get("permissions")
