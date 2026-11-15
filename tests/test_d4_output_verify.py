"""Çıktı doğrulayıcı: ffmpeg sızıntısı, tarama, Remotion kuralı, ".." yolu (A2-30..A2-33)."""

from __future__ import annotations

import asyncio

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import output_verify
from fusion_cli.engines.agent.output_verify import (
    OutputPathVerifier,
    _same_name_elsewhere,
    requested_outputs_in,
)


async def test_ffmpeg_zaman_asiminda_surec_oldurulur(monkeypatch, tmp_path):
    olduruldu: list[bool] = []

    class _Surec:
        async def communicate(self):
            await asyncio.sleep(10)

        def kill(self):
            olduruldu.append(True)

        async def wait(self):
            return 0

    async def _baslat(*args, **kwargs):
        return _Surec()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _baslat)
    monkeypatch.setattr(output_verify, "FFMPEG_TIMEOUT_S", 0.01)

    assert await output_verify._ffmpeg_stderr("ffmpeg", tmp_path / "v.mp4", "blackdetect") is None
    assert olduruldu == [True]


def test_ayni_adli_dosya_aranirken_node_modules_gezilmez(tmp_path):
    (tmp_path / "node_modules" / "p").mkdir(parents=True)
    (tmp_path / "node_modules" / "p" / "video.mp4").write_bytes(b"x")
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "video.mp4").write_bytes(b"x")

    assert _same_name_elsewhere(tmp_path, "video.mp4") == ["video/video.mp4"]


def test_ust_dizine_cikan_yol_istenen_cikti_sayilmaz():
    assert requested_outputs_in("Videoyu `../x.mp4` olarak kaydet") == ()
    assert requested_outputs_in("Videoyu `out/x.mp4` olarak kaydet") == ("out/x.mp4",)


async def _donuk_video(monkeypatch, tmp_path, task_kinds):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "ders.mp4").write_bytes(b"x")

    async def _kanit(path, yol, expected):
        return output_verify._VideoEvidence()

    async def _siyah(path):
        return (), 30.0

    async def _donuk(path, toplam):
        return ((1.0, 29.0),)

    monkeypatch.setattr(output_verify, "_video_evidence", _kanit)
    monkeypatch.setattr(output_verify, "measure_black", _siyah)
    monkeypatch.setattr(output_verify, "measure_freeze", _donuk)
    baglam = ToolContext(root=tmp_path, task_kinds=set(task_kinds))
    baglam.requested_outputs.add("out/ders.mp4")
    baglam.touched.add(tmp_path / "x.txt")
    return await OutputPathVerifier(baglam).verify()


async def test_donukluk_kurali_remotion_disi_videoda_uygulanmaz(monkeypatch, tmp_path):
    assert (await _donuk_video(monkeypatch, tmp_path, ())).ok


async def test_donukluk_kurali_remotion_gorevinde_uygulanir(monkeypatch, tmp_path):
    sonuc = await _donuk_video(monkeypatch, tmp_path, {"remotion"})
    assert not sonuc.ok and "DONUK" in sonuc.findings[0]
