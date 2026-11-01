"""Kalıcı kabuk dizini (#126): Bash `cd`'si sonraki komutlara taşınır, `CwdChanged` tetikler.

Claude Code: çalışma dizini komutlar arasında sürer; proje dışına çıkınca köke sıfırlanır;
`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` her komuttan sonra köke döner. Denetimler
(korumalı yol, silme önizlemesi) komutun gerçekte çalıştığı dizini hesaba katar.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.core.shell_cwd import MAINTAIN_ENV, ShellCwd, split_marker, wrap
from fusion_cli.core.tools import Tool, ToolContext
from fusion_cli.engines.agent.approval import build_request, resolve_request
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.tools import shell
from fusion_cli.tools.shell import run_shell
from fusion_cli.tools.shell_cwd_check import checked_command

from .fakes import model_result, tool_call
from .test_hooks_loop import _arac_mesajlari, _kayit_kancasi, _satirlar, _tur

_KABUK = Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None)


def _proje(tmp_path: Path) -> Path:
    root = (tmp_path / "proje").resolve()
    (root / "alt" / "ic").mkdir(parents=True)
    return root


def test_cd_sonraki_komuta_tasinir(tmp_path, monkeypatch):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = _proje(tmp_path)
    context = ToolContext(root=root)
    ilk = run_shell({"command": "cd alt"}, context)
    assert ilk.ok
    assert "__FUSION_CWD_" not in ilk.output
    assert "sonraki komutlar burada başlar" in ilk.output
    ikinci = run_shell({"command": "pwd"}, context)
    assert str(root / "alt") in ikinci.output
    assert "__FUSION_CWD_" not in ikinci.output


def test_cikis_kodu_korunur_ve_dizin_yine_kaydedilir(tmp_path, monkeypatch):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = _proje(tmp_path)
    context = ToolContext(root=root)
    sonuc = run_shell({"command": "cd alt && false"}, context)
    assert not sonuc.ok
    assert sonuc.output.startswith("(çıkış kodu 1)")
    assert context.shell_cwd.path == root / "alt"


def test_proje_disina_cikan_cd_koke_sifirlanir(tmp_path, monkeypatch):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = _proje(tmp_path)
    context = ToolContext(root=root)
    run_shell({"command": "cd alt"}, context)
    sonuc = run_shell({"command": "cd /"}, context)
    assert "sıfırlandı" in sonuc.output
    assert context.shell_cwd.path is None
    assert str(root) in run_shell({"command": "pwd"}, context).output


def test_maintain_project_working_dir_her_komutta_koke_doner(tmp_path, monkeypatch):
    monkeypatch.setenv(MAINTAIN_ENV, "1")
    root = _proje(tmp_path)
    context = ToolContext(root=root)
    run_shell({"command": "cd alt"}, context)
    assert context.shell_cwd.path is None
    assert str(root / "alt") not in run_shell({"command": "pwd"}, context).output


def test_sade_rm_kalici_dizindeki_dosyayi_copte_tasir(tmp_path, monkeypatch):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    monkeypatch.setattr(shell, "trash_dir", lambda: tmp_path / "cop")
    root = _proje(tmp_path)
    (root / "alt" / "x.txt").write_text("a", encoding="utf-8")
    (root / "x.txt").write_text("kok", encoding="utf-8")
    context = ToolContext(root=root, shell_cwd=ShellCwd(path=root / "alt"))
    sonuc = run_shell({"command": "rm x.txt"}, context)
    assert sonuc.ok, sonuc.output
    assert not (root / "alt" / "x.txt").exists()
    assert (root / "x.txt").exists()


def test_isaret_ayristirma_komut_ciktisini_korur():
    metin, dizin = split_marker("merhaba\n\n__M__/tmp/a\n", "__M__")
    assert metin == "merhaba\n"
    assert dizin == Path("/tmp/a")
    assert split_marker("sahte __M__/x", "__N__") == ("sahte __M__/x", None)
    assert "{ echo 1\n}" in wrap("echo 1", "__M__")


def test_stdout_yonlendiren_komutta_isaret_dosyaya_karismaz_cd_korunur(tmp_path, monkeypatch):
    # `exec > dosya` kabuğun stdout'unu kalıcı değiştirir; işaret ayrı tanımlayıcıdan yazılır.
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = _proje(tmp_path)
    context = ToolContext(root=root)
    sonuc = run_shell({"command": "cd alt; exec > out.txt; echo hi"}, context)
    assert sonuc.ok, sonuc.output
    assert (root / "alt" / "out.txt").read_text(encoding="utf-8") == "hi\n"
    assert "__FUSION_CWD_" not in sonuc.output
    assert context.shell_cwd.path == root / "alt"


def test_arka_plan_isi_isaret_tanimlayicisini_tutmaz(tmp_path, monkeypatch):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = _proje(tmp_path)
    context = ToolContext(root=root)
    sonuc = run_shell({"command": "ls -l /dev/fd/ 2>/dev/null | awk '{print $9}'"}, context)
    assert sonuc.ok, sonuc.output
    assert "9" not in sonuc.output.split()


def test_denetim_komutu_kalici_dizini_hesaba_katar(tmp_path):
    root = _proje(tmp_path)
    assert checked_command("ls", root, root) == "ls"
    assert checked_command("touch ../.git/x", root / "alt", root) == "cd alt && touch ../.git/x"
    assert checked_command("rm -f x ../y", root / "alt" / "ic", root) == "rm -f alt/ic/x alt/y"


def test_korumali_yol_denetimi_kalici_dizinde_de_yakalar(tmp_path):
    root = _proje(tmp_path)
    tool = _KABUK
    args = {"command": "touch ../.git/config"}
    # Kökte `../.git` proje dışıdır; izin alanı (#59) proje dışındaki `.git`'i de korur, bu
    # yüzden yalnız alt dizinde denetimin kalıcı kabuk dizinine göre yapıldığı sınanır.
    altta = build_request(tool, args, root=root, shell_cwd=root / "alt")
    assert altta.danger is not None and ".git" in altta.danger
    # Kart ve kancalar asıl komutu görür; yalnız denetim eşdeğeri değişir.
    assert altta.args["command"] == "touch ../.git/config"
    assert altta.checked_command == "cd alt && touch ../.git/config"


async def test_resolve_request_baglamin_kabuk_dizinini_kullanir(tmp_path):
    root = _proje(tmp_path)
    tool = _KABUK
    context = ToolContext(root=root, shell_cwd=ShellCwd(path=root / "alt"))
    istek = await resolve_request(
        tool, {"command": "touch ../.git/config"}, root=root, context=context
    )
    assert istek.danger is not None and ".git" in istek.danger


async def test_bash_cd_cwdchanged_tetikler_ve_turlar_arasi_surer(monkeypatch, tmp_path):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = tmp_path.resolve()
    (root / "alt").mkdir()
    kayit = tmp_path / "cwd.jsonl"
    hook = _kayit_kancasi(tmp_path, HookEvent.CWD_CHANGED, kayit)
    session = HookSession(root=root, loader=lambda: HookSet((hook,)))
    cd = model_result(tool_calls=[tool_call("run_shell", command="cd alt")])
    await _tur(monkeypatch, root, [cd, model_result("ok")], session)
    olaylar = _satirlar(kayit)
    assert [(o["old_cwd"], o["new_cwd"]) for o in olaylar] == [(str(root), str(root / "alt"))]
    assert session.shell_cwd == root / "alt"
    # Yeni tur yeni ToolContext kurar; dizin oturumdan gelir, kanca girdisi `cwd` odur.
    pwd = model_result(tool_calls=[tool_call("run_shell", command="pwd")])
    outcome, _, _, _ = await _tur(monkeypatch, root, [pwd, model_result("ok")], session)
    assert str(root / "alt") in _arac_mesajlari(outcome)[0]
    assert len(_satirlar(kayit)) == 1


async def test_cd_komutu_cwdchanged_tetiklemez_dizin_degismezse(monkeypatch, tmp_path):
    monkeypatch.delenv(MAINTAIN_ENV, raising=False)
    root = tmp_path.resolve()
    kayit = tmp_path / "cwd.jsonl"
    hook = _kayit_kancasi(tmp_path, HookEvent.CWD_CHANGED, kayit)
    session = HookSession(root=root, loader=lambda: HookSet((hook,)))
    ls = model_result(tool_calls=[tool_call("run_shell", command="ls")])
    await _tur(monkeypatch, root, [ls, model_result("ok")], session)
    assert _satirlar(kayit) == []
