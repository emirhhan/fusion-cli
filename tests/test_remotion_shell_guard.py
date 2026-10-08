"""Kabuk çıkışı kit bütünlüğü kaybolunca başarı sayılamaz."""

import subprocess

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import jobs, shell
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


async def _context(root):
    context = ToolContext(root=root)
    assert (
        await scaffold_remotion(
            {
                "path": "video",
                "composition_id": "Video",
                "timeout_s": 10,
                "scenes": [{"id": "intro", "kind": "custom", "duration": 90}],
            },
            context,
        )
    ).ok
    return context


@pytest.mark.parametrize("background", [False, True])
async def test_bozuk_kit_kabuk_isini_baslatmaz(tmp_path, monkeypatch, background):
    context = await _context(tmp_path)
    (tmp_path / "video/src/kit/LayoutAudit.tsx").write_text("bozuk")
    calls = []
    monkeypatch.setattr(shell.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(shell, "start_job", lambda *a, **k: calls.append(a))
    result = shell.run_shell({"command": "echo test", "background": background}, context)
    assert not result.ok and calls == []


async def test_senkron_exit_sifir_sonrasi_hash_degismesi_basari_degil(tmp_path, monkeypatch):
    context = await _context(tmp_path)
    monkeypatch.setattr(shell, "_shell_env", lambda: {})

    def run(*args, **kwargs):
        (tmp_path / "video/src/index.tsx").write_text("değişti")
        return subprocess.CompletedProcess(args, 0, "render tamamlandı", "")

    monkeypatch.setattr(shell.subprocess, "run", run)
    result = shell.run_shell({"command": "echo test"}, context)
    assert not result.ok and "çıkış kodu 0" in result.output
    assert "render tamamlandı" in result.output


async def test_completed_job_exit_sifir_kit_degisimini_reddeder(tmp_path, monkeypatch):
    context = await _context(tmp_path)
    folder = tmp_path / ".fusion/is"
    folder.mkdir(parents=True)
    (folder / "abc12345.cmd").write_text("render")
    (folder / "abc12345.exit").write_text("0")
    (folder / "abc12345.log").write_text("tamamlandı")
    from fusion_cli.core.job_evidence import JobCompletion, JobPhase

    receipt = JobCompletion("abc12345", "render", JobPhase.COMPLETED, exit_code=0)
    monkeypatch.setattr(jobs, "observe_delivery", lambda *a: receipt)
    (tmp_path / "video/src/kit/LayoutAudit.tsx").write_text("bozuk")
    result = jobs.job_status({"id": "abc12345"}, context)
    assert not result.ok and result.is_observation
    assert "çıkış kodu 0" in result.output
    assert result.job_completion is receipt and receipt.exit_code == 0


async def test_kitsiz_ve_editable_kaynak_kabugu_engellemez(tmp_path, monkeypatch):
    context = await _context(tmp_path)
    (tmp_path / "video/src/Composition.tsx").write_text("düzenlendi")
    monkeypatch.setattr(shell, "_shell_env", lambda: {})
    monkeypatch.setattr(
        shell.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "ok", "")
    )
    assert shell.run_shell({"command": "echo test"}, context).ok
    assert shell.run_shell({"command": "echo test"}, ToolContext(root=tmp_path)).ok


async def test_hash_okuma_hatasi_kabuk_baslangicini_engeller(tmp_path, monkeypatch):
    from fusion_cli.tools import remotion_shell_guard

    context = await _context(tmp_path)
    calls = []

    def check(*args):
        raise OSError("dosya okunamadı")

    monkeypatch.setattr(remotion_shell_guard, "check_packaged", check)
    monkeypatch.setattr(shell, "start_job", lambda *a, **k: calls.append(a))
    result = shell.run_shell({"command": "echo test", "background": True}, context)
    assert not result.ok and "okunamadı" in result.output and calls == []


async def test_guvenli_cop_erken_donusu_kit_silinmesini_basari_saymaz(tmp_path, monkeypatch):
    context = await _context(tmp_path)
    target = tmp_path / "video/src/kit/LayoutAudit.tsx"

    def move(*args, **kwargs):
        target.unlink()
        return (), ()

    monkeypatch.setattr(shell, "move_to_trash", move)
    monkeypatch.setattr(shell, "trash_dir", lambda: tmp_path / "trash")
    result = shell.run_shell({"command": "rm video/src/kit/LayoutAudit.tsx"}, context)
    assert not result.ok
    assert "çıkış kodu 0" in result.output and "Fusion çöpüne taşındı" in result.output
