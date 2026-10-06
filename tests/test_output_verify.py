"""İstenen çıktı dosyası istenen yerde mi (`output_verify`).

Ölçüldü (6 Ekim 2026, dalga23 Remotion): görev "`out/video.mp4` olarak render et"
dedi; Fusion projeyi `video/` alt klasörüne kurdu, videoyu `video/out/video.mp4`
olarak üretti ve "tamamlandı" dedi. İstenen yerde dosya yoktu.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.output_verify import OutputPathVerifier, requested_outputs_in

REMOTION = "Remotion ile 10 saniyelik bir video üret. Videoyu `out/video.mp4` olarak render et."


def test_istekte_acikca_yazilan_cikti_yolu_bulunur():
    assert requested_outputs_in(REMOTION) == ("out/video.mp4",)
    assert requested_outputs_in("Çıktı çalışma klasöründe `index.html` olsun.") == ("index.html",)


def test_okunacak_ya_da_duzenlenecek_dosya_cikti_sayilmaz():
    assert requested_outputs_in("`src/app.py` içindeki hatayı düzelt") == ()
    assert requested_outputs_in("`config.yaml` dosyasını oku ve özetle") == ()
    assert requested_outputs_in("https://x.com/a.png adresine bak") == ()


async def test_istenen_yerde_yoksa_ve_baska_yerde_uretildiyse_soylenir(tmp_path: Path):
    (tmp_path / "video" / "out").mkdir(parents=True)
    (tmp_path / "video" / "out" / "video.mp4").write_bytes(b"x")
    context = ToolContext(root=tmp_path)
    context.requested_outputs.update(requested_outputs_in(REMOTION))
    context.touched.add(tmp_path / "video" / "src" / "Composition.tsx")

    sonuc = await OutputPathVerifier(context).verify()

    assert not sonuc.ok
    assert "out/video.mp4" in sonuc.findings[0]
    assert "video/out/video.mp4" in sonuc.findings[0]


async def test_istenen_yerde_varsa_gecer(tmp_path: Path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "video.mp4").write_bytes(b"x")
    context = ToolContext(root=tmp_path)
    context.requested_outputs.add("out/video.mp4")
    context.touched.add(tmp_path / "src.tsx")

    assert (await OutputPathVerifier(context).verify()).ok


async def test_hicbir_sey_yazilmadiysa_soz_soylemez(tmp_path: Path):
    context = ToolContext(root=tmp_path)
    context.requested_outputs.add("out/video.mp4")

    assert (await OutputPathVerifier(context).verify()).ok


def test_ffmpeg_siyah_bolum_ciktisi_okunur():
    from fusion_cli.engines.agent.output_verify import black_segments

    log = (
        "[blackdetect @ 0x1] black_start:0 black_end:0.333 black_duration:0.333\n"
        "[blackdetect @ 0x1] black_start:3.766 black_end:9.966 black_duration:6.2\n"
    )
    assert black_segments(log) == ((0.0, 0.333), (3.766, 9.966))


async def test_istenen_video_uzun_sure_siyahsa_soylenir(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import output_verify

    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "video.mp4").write_bytes(b"x")
    context = ToolContext(root=tmp_path)
    context.requested_outputs.add("out/video.mp4")
    context.touched.add(tmp_path / "src.tsx")

    async def _olc(path):
        return ((0.0, 0.3), (3.77, 9.97)), 10.0

    monkeypatch.setattr(output_verify, "measure_black", _olc)

    sonuc = await OutputPathVerifier(context).verify()

    assert not sonuc.ok
    assert "3.8" in sonuc.findings[0] and "siyah" in sonuc.findings[0]
