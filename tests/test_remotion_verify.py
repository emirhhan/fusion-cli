"""Remotion projesinde CSS animasyonu yasak (`remotion_verify`).

Ölçüldü (6 Ekim 2026, dalga23): beceri metni "CSS animation KULLANMA" diyordu; model
`animation: 'pulse 3s ease-in-out infinite'` yazdı. Render kare kare yapılır, CSS
animasyonu videoda oynamaz; kural metinle değil kapıyla tutulur.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.remotion_verify import RemotionCssVerifier


def _proje(tmp_path: Path, kod: str, *, remotion: bool = True) -> ToolContext:
    (tmp_path / "video" / "src").mkdir(parents=True)
    bagimlilik = '"remotion": "4.0.0"' if remotion else '"react": "18"'
    (tmp_path / "video" / "package.json").write_text(f'{{"dependencies": {{{bagimlilik}}}}}')
    dosya = tmp_path / "video" / "src" / "Composition.tsx"
    dosya.write_text(kod)
    context = ToolContext(root=tmp_path)
    context.touched.add(dosya)
    return context


async def test_remotion_projesinde_css_animasyonu_bulgu_verir(tmp_path: Path):
    context = _proje(tmp_path, "<div style={{ animation: 'pulse 3s ease-in-out infinite' }} />")

    sonuc = await RemotionCssVerifier(context).verify()

    assert not sonuc.ok
    assert "Composition.tsx:1" in sonuc.findings[0]
    assert "interpolate" in sonuc.findings[0]


async def test_kare_tabanli_hareket_gecer(tmp_path: Path):
    kod = "const o = interpolate(frame, [0, 20], [0, 1]);\n<div style={{ opacity: o }} />"
    assert (await RemotionCssVerifier(_proje(tmp_path, kod)).verify()).ok


async def test_remotion_olmayan_projede_soz_soylemez(tmp_path: Path):
    context = _proje(tmp_path, "a { transition: opacity .2s }", remotion=False)
    assert (await RemotionCssVerifier(context).verify()).ok
