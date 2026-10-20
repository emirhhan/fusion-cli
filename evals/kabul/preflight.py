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

from evals.kabul.engine_options import comparison_validity, selected_engine
from evals.kabul.model import Area
from evals.selected_probe import ProbeEvidence, probe_command, run_owned_probe

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
    evidence: ProbeEvidence | None = None


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


def _model_probe(
    config: Path | None, source: Path | None = None, manifest: Path | None = None
) -> PreflightItem:
    """Ana modele tek kısa tur: yanıt yoksa uzun koşular zaten ölçülemez."""
    ortam = {**os.environ, **({"FUSION_CONFIG": str(config)} if config else {})}
    if source is not None or manifest is not None:
        return _selected_model_probe(source, manifest, ortam)
    fusion = Path(sys.executable).with_name("fusion")
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


def run_preflight(
    areas: Iterable[Area],
    workroot: Path,
    config: Path | None,
    *,
    engine_source: Path | None = None,
    engine_manifest: Path | None = None,
) -> PreflightReport:
    """Bütün ön-kontrolleri çalıştır; model sondası en sona (en pahalısı)."""
    alanlar = tuple(areas)
    items = (_disk(workroot), *_executables(alanlar))
    if not all(item.passed for item in items):
        return PreflightReport(items)
    model = (
        _model_probe(config, engine_source, engine_manifest)
        if engine_source is not None or engine_manifest is not None
        else _model_probe(config)
    )
    return PreflightReport((*items, model))


def _selected_model_probe(
    source: Path | None, manifest: Path | None, environment: dict[str, str]
) -> PreflightItem:
    """Seçilmiş aynı süreç ve actual config yanıtı; kalıcı durum bilinmiyor kalır."""
    with tempfile.TemporaryDirectory(prefix="kabul-secili-onkontrol-") as temporary:
        root = Path(temporary)
        engine = selected_engine(source, manifest, root)
        if engine is None:
            return PreflightItem("model", False, "Açık motor seçimi eksik.")
        try:
            result = run_owned_probe(
                probe_command(
                    engine.selection.source_root,
                    engine.manifest,
                    root,
                    MODEL_PROBE_TASK,
                    MODEL_PROBE_TIMEOUT_S,
                ),
                cwd=root,
                env=environment,
                timeout=MODEL_PROBE_TIMEOUT_S,
            )
            driver = json.loads(result.stdout)
            validity = comparison_validity(driver, engine)
            turns = driver.get("turlar") if isinstance(driver, dict) else None
            ok = (
                result.returncode == 0
                and validity.config_verified
                and isinstance(turns, list)
                and len(turns) == 1
                and isinstance(turns[0], dict)
                and turns[0].get("ok") is True
                and driver.get("araclar") == []
            )
        except (ValueError, OSError, subprocess.TimeoutExpired):
            return PreflightItem("model", False, "Seçilmiş model/süreç kanıtı doğrulanmadı.")
    evidence = (
        ProbeEvidence(
            driver["motor_kaniti"]["pid"],
            validity.source_digest,
            validity.config_digests,
            engine.selection.requested_revision,
        )
        if ok and validity.source_digest is not None
        else None
    )
    return PreflightItem(
        "model",
        ok,
        "Seçilmiş süreç/config yanıtı doğrulandı; kalıcı öğrenim/cache bilinmiyor."
        if ok
        else "Seçilmiş model yanıtı veya kanıtı eksik/geçersiz.",
        evidence,
    )
