"""Ajanın görsel aracı: doğru üretici, tam ölçü, srcset ve sayfaya konacak <img>."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from fusion_cli.core.errors import PathAccessError
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import image_tools
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.providers.image_generation import GenerationResult, ImageChoice
from fusion_cli.providers.nim_image import flux_size_for
from fusion_cli.providers.web_image import GeneratedImage
from fusion_cli.tools.image_ops import fit_cover, img_tag, optimize_image, srcset_variants
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config

_NIM = ImageChoice("nvidia_nim/black-forest-labs/flux.1-dev", "FLUX.1-dev", False, True)
_KLEIN = ImageChoice("nvidia_nim/black-forest-labs/flux.2-klein-4b", "FLUX.2", False, False)
_GEMINI = ImageChoice("gemini_web/main", "Gemini", True, False)


def _png(path: Path, size: tuple[int, int], color=(200, 40, 40)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_ajan_tam_olcu_alan_ureticiyi_secer():
    assert image_tools.pick_generator((_GEMINI, _KLEIN, _NIM)) == _NIM
    assert image_tools.pick_generator((_GEMINI, _KLEIN)) == _KLEIN
    assert image_tools.pick_generator((_GEMINI,)) == _GEMINI
    assert image_tools.pick_generator(()) is None


@pytest.mark.parametrize(
    ("hedef", "beklenen_oran"), [((1920, 1080), 16 / 9), ((1080, 1920), 9 / 16), ((1200, 630), 1.9)]
)
def test_flux_olcusu_oranı_korur_ve_ucun_sinirinda_kalir(hedef, beklenen_oran):
    genislik, yukseklik = flux_size_for(*hedef)

    assert genislik % 32 == 0 and yukseklik % 32 == 0
    assert 672 <= genislik <= 1568 and 672 <= yukseklik <= 1568
    assert abs(genislik / yukseklik - beklenen_oran) < 0.1


def test_kapla_kirp_tam_olcuye_getirir_ve_buyutmeyi_soyler(tmp_path):
    kaynak = _png(tmp_path / "k.png", (1376, 768))

    sonuc = fit_cover(kaynak, tmp_path / "hero.webp", 1920, 1080)

    with Image.open(sonuc.path) as gorsel:
        assert (gorsel.width, gorsel.height, gorsel.format) == (1920, 1080, "WEBP")
    assert sonuc.upscaled and sonuc.cropped


def test_srcset_buyutme_yapmaz(tmp_path):
    kaynak = fit_cover(_png(tmp_path / "k.png", (1200, 800)), tmp_path / "g.webp", 1200, 800)

    kopyalar = srcset_variants(kaynak.path)

    assert [kopya.width for kopya in kopyalar] == [640, 1024]
    assert all(kopya.path.suffix == ".webp" for kopya in kopyalar)


def test_img_onerisi_olcu_alt_ve_oncelik_tasir(tmp_path):
    kaynak = fit_cover(_png(tmp_path / "k.png", (1600, 900)), tmp_path / "a" / "h.webp", 1600, 900)
    kopyalar = srcset_variants(kaynak.path)

    etiket = img_tag(kaynak, alt='Kahve "fincanı"', root=tmp_path, eager=True, variants=kopyalar)

    assert 'src="a/h.webp"' in etiket
    assert 'width="1600" height="900"' in etiket
    assert 'alt="Kahve &quot;fincanı&quot;"' in etiket
    assert 'fetchpriority="high"' in etiket
    assert "a/h-640w.webp 640w" in etiket


def test_desteklenmeyen_uzanti_acik_hata_verir(tmp_path):
    from fusion_cli.tools.image_ops import ImageOpsError

    with pytest.raises(ImageOpsError, match="Desteklenmeyen"):
        fit_cover(_png(tmp_path / "k.png", (100, 100)), tmp_path / "x.gif", 50, 50)


def test_optimize_image_png_yi_webp_ye_cevirir(tmp_path):
    _png(tmp_path / "foto.png", (1400, 1000))

    sonuc = optimize_image({"path": "foto.png", "alt": "foto"}, ToolContext(root=tmp_path))

    assert sonuc.output.startswith("Hazır:")
    assert (tmp_path / "foto.webp").is_file()
    assert 'loading="lazy"' in sonuc.output


def _deps(tmp_path) -> AgentDeps:
    return AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


async def test_generate_image_uretir_kirpar_ve_yerlestirme_onerir(tmp_path, monkeypatch):
    alinan: dict[str, object] = {}

    async def _render(config, choice, prompt, out_dir, *, size=None, reference=None, environ=None):
        alinan.update(choice=choice, prompt=prompt, size=size)
        gorsel = _png(out_dir / "uretilen.png", size or (1024, 1024))
        return GenerationResult("FLUX.1-dev", (GeneratedImage(gorsel, *gorsel_olcu(gorsel)),))

    monkeypatch.setattr(image_tools, "image_choices", lambda _config: (_GEMINI, _NIM))
    monkeypatch.setattr(image_tools, "render_images", _render)
    arac = image_tools.generate_image_tool(_deps(tmp_path))
    assert arac is not None

    sonuc = await arac.run(
        {
            "prompt": "sıcak ışıklı bir kafe",
            "width": 1920,
            "height": 1080,
            "path": "assets/hero.webp",
            "alt": "Kafenin içi",
            "ilk_ekran": True,
        },
        ToolContext(root=tmp_path),
    )

    assert alinan["choice"] == _NIM.value
    assert alinan["size"] == flux_size_for(1920, 1080)
    with Image.open(tmp_path / "assets/hero.webp") as gorsel:
        assert gorsel.size == (1920, 1080)
    assert 'fetchpriority="high"' in sonuc.output
    assert "büyütüldü" in sonuc.output
    assert (tmp_path / "assets/hero-1024w.webp").is_file()


async def test_web_ureticisine_oran_istemde_soylenir(tmp_path, monkeypatch):
    alinan: dict[str, object] = {}

    async def _render(config, choice, prompt, out_dir, *, size=None, reference=None, environ=None):
        alinan.update(prompt=prompt, size=size)
        gorsel = _png(out_dir / "u.png", (1024, 559))
        return GenerationResult("Gemini", (GeneratedImage(gorsel, 1024, 559),))

    monkeypatch.setattr(image_tools, "image_choices", lambda _config: (_GEMINI,))
    monkeypatch.setattr(image_tools, "render_images", _render)
    arac = image_tools.generate_image_tool(_deps(tmp_path))
    assert arac is not None

    await arac.run(
        {"prompt": "logo", "width": 800, "height": 600, "path": "logo.png"},
        ToolContext(root=tmp_path),
    )

    assert alinan["size"] is None
    assert "800:600" in str(alinan["prompt"])


async def test_uretici_yoksa_arac_sunulmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(image_tools, "image_choices", lambda _config: ())

    assert image_tools.generate_image_tool(_deps(tmp_path)) is None


async def test_paralel_ajan_yazma_alani_disina_gorsel_yazamaz(tmp_path, monkeypatch):
    monkeypatch.setattr(image_tools, "image_choices", lambda _config: (_NIM,))
    arac = image_tools.generate_image_tool(_deps(tmp_path))
    assert arac is not None
    baglam = replace(ToolContext(root=tmp_path), write_scope=(tmp_path / "css",))

    with pytest.raises(PathAccessError):
        await arac.run(
            {"prompt": "x", "width": 100, "height": 100, "path": "assets/a.webp"}, baglam
        )


def gorsel_olcu(path: Path) -> tuple[int, int]:
    with Image.open(path) as gorsel:
        return gorsel.size
