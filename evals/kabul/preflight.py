"""Kabul koşusu öncesi ortam ön-kontrolü.

Geçmişte ölçümü bozan ortam olayları (disk dolu, eksik php/ffmpeg, model
yanıt vermiyor) koşu başladıktan sonra "başarısız" diye kaydediliyordu. Burada
koşudan ÖNCE yakalanır: ön-kontrol geçmezse koşu başlamaz ve sonuç `gecersiz`
yazılır; model ya da Fusion suçlanmaz.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from evals.kabul.model import Area

#: Uzun koşu WordPress çekirdeği, görseller ve video ürettiği için alan bırakılır
#: (24 Eylül'de 20 MB boş disk koşuyu ENOSPC ile düşürdü).
MIN_FREE_DISK_GB = 5.0
#: Ana modelin tek kısa tura yanıt vermesi için süre; NIM ilk yanıtı bazen 30 sn+.
MODEL_PROBE_TIMEOUT_S = 240
MODEL_PROBE_TASK = "Yalnız 'tamam' yaz. Araç kullanma."
#: TurnOutcome.status değerlerinden "model yanıt verdi" sayılanlar.
_OK_STATUSES = ("completed", "ok")


@dataclass(frozen=True, slots=True)
class PreflightItem:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    items: tuple[PreflightItem, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.items)

    def failures(self) -> str:
        return "; ".join(f"{item.name}: {item.detail}" for item in self.items if not item.passed)


def _disk(path: Path) -> PreflightItem:
    bos = shutil.disk_usage(path).free / 1024**3
    return PreflightItem("disk", bos >= MIN_FREE_DISK_GB, f"{bos:.1f} GB boş")


def _executables(areas: Iterable[Area]) -> tuple[PreflightItem, ...]:
    gerekli = sorted({ad for area in areas for ad in area.required_executables})
    eksik = [ad for ad in gerekli if shutil.which(ad) is None]
    return (PreflightItem("araclar", not eksik, "eksik: " + ", ".join(eksik) if eksik else "tam"),)


def _model_probe(config: Path | None) -> PreflightItem:
    """Ana modele tek kısa tur: yanıt yoksa uzun koşular zaten ölçülemez."""
    fusion = Path(sys.executable).with_name("fusion")
    ortam = {**os.environ, **({"FUSION_CONFIG": str(config)} if config else {})}
    with tempfile.TemporaryDirectory(prefix="kabul-onkontrol-") as kok:
        try:
            sonuc = subprocess.run(
                [str(fusion), "agent", MODEL_PROBE_TASK, "--json"],
                cwd=kok,
                env=ortam,
                capture_output=True,
                text=True,
                timeout=MODEL_PROBE_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return PreflightItem("model", False, f"{MODEL_PROBE_TIMEOUT_S} sn içinde yanıt yok")
    for satir in reversed(sonuc.stdout.splitlines()):
        try:
            olay = json.loads(satir)
        except ValueError:
            continue
        if olay.get("event") == "TurnOutcome":
            return PreflightItem(
                "model", olay.get("status") in _OK_STATUSES, str(olay.get("status"))
            )
    return PreflightItem("model", False, (sonuc.stderr or "çıktı yok")[-200:])


def run_preflight(areas: Iterable[Area], workroot: Path, config: Path | None) -> PreflightReport:
    """Bütün ön-kontrolleri çalıştır; model sondası en sona (en pahalısı)."""
    alanlar = tuple(areas)
    items = (_disk(workroot), *_executables(alanlar))
    if not all(item.passed for item in items):
        return PreflightReport(items)
    return PreflightReport((*items, _model_probe(config)))
