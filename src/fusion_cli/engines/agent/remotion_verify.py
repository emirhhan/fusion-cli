"""Remotion projesinde CSS animasyonu: render'da oynamaz, kapıda yakalanır.

Ölçüldü (6 Ekim 2026, dalga23 Remotion): yerleşik beceri "CSS `transition`,
`animation`, `@keyframes` KULLANMA" diyordu; model yine de
`animation: 'pulse 3s ease-in-out infinite'` yazdı ve "tamamlandı" dedi. Remotion her
kareyi ayrı çizer; CSS animasyonu videoda donuk kalır. Metinle verilen kural ücretsiz
modelde tutmadı; yalnız dokunulan dosyalara bakan deterministik bir kapı tutar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...core.tools import ToolContext
from ...core.verification import VerificationResult

_SUFFIXES = frozenset({".tsx", ".ts", ".jsx", ".js", ".css"})
#: CSS animasyonu işaretleri (satır içi stil, CSS dosyası, Tailwind sınıfı).
_CSS_MOTION = re.compile(
    r"\banimation(?:Name)?\s*:|\btransition\s*:|@keyframes\b|\banimate-[a-z]", re.IGNORECASE
)
#: Bir projede en çok bildirilen satır (bulgu listesi kısa kalır).
_MAX_FINDINGS = 5


class RemotionCssVerifier:
    """Dokunulan Remotion kaynaklarında CSS animasyonu/geçişi var mı?"""

    def __init__(self, context: ToolContext) -> None:
        self._context = context

    async def verify(self) -> VerificationResult:
        bulgular: list[str] = []
        for path in sorted(self._context.touched):
            if path.suffix.lower() not in _SUFFIXES or not _in_remotion_project(path):
                continue
            bulgular.extend(_violations(path, self._context.root))
            if len(bulgular) >= _MAX_FINDINGS:
                break
        if not bulgular:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False,
            summary=f"Remotion kaynağında {len(bulgular)} CSS animasyonu (videoda oynamaz)",
            findings=tuple(bulgular[:_MAX_FINDINGS]),
        )


def _violations(path: Path, root: Path) -> list[str]:
    try:
        satirlar = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    try:
        ad = path.relative_to(root).as_posix()
    except ValueError:
        ad = path.name
    return [
        f"{ad}:{no}: CSS animasyonu/geçişi ({satir.strip()[:80]}) — Remotion kare kare "
        "render eder, bu videoda oynamaz. Hareketi useCurrentFrame() + interpolate()/"
        "spring() ile hesapla."
        for no, satir in enumerate(satirlar, start=1)
        if _CSS_MOTION.search(satir)
    ]


def _in_remotion_project(path: Path) -> bool:
    """Dosyanın en yakın package.json'ı remotion'a bağımlı mı?"""
    for folder in path.parents:
        paket = folder / "package.json"
        if not paket.is_file():
            continue
        try:
            veri = json.loads(paket.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        bagimliliklar = {**veri.get("dependencies", {}), **veri.get("devDependencies", {})}
        return "remotion" in bagimliliklar
    return False
