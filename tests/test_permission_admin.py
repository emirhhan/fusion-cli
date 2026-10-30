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
