"""Kabul koşularını paralel ve kademeli başlatan koşucu.

Her koşu kendi çalışma klasöründe, masaüstü çekirdeğini (`fusion app`) süren
`evals.live_drive` ile yürür (Fusion Browser yalnız bu yolda bağlanabilir).
Paralellik iki gerçek kaynakla sınırlıdır:

- NIM model başına dakikada ~40 istek: tek uzun koşu ~2 istek/dk yapıyor
  (17. koşu: 169 çağrı / 90 dk), yani birkaç koşu bu sınırın altında kalır.
- Paylaşılan Gemini öğretmeni ve makinenin belleği: koşular `stagger_s` arayla
  başlatılır ki öğretmene giden plan istekleri ve WordPress kurulumları üst üste
  binmesin.

Chrome eklentisi tek bir küresel eşleşme dosyası kullandığı için eklenti isteyen
koşular birbirini bekler (kilit).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from evals.kabul.model import Area, Inspection, RunMetrics, RunRecord, classify

_LOG = logging.getLogger(__name__)
#: Sürücü `python -m evals.live_drive` ile depo kökünden çalışır.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: live_drive'ın kendi zaman aşımının üstüne süreç kapanışı için pay.
DRIVER_GRACE_S = 120
#: Eklenti eşleşmesi için beklenecek süre (kullanıcının Chrome'u açık olmalı).
CHROME_PAIRING_S = 120


@dataclass(frozen=True, slots=True)
class Job:
    area: Area
    attempt: int
    workdir: Path


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    parallel: int
    stagger_s: float
    config: Path | None


def _driver_command(job: Job, root: Path, task: str) -> list[str]:
    komut = [
        sys.executable, "-m", "evals.live_drive",
        "--kok", str(root), "--mod", "auto", "--sure", str(job.area.timeout_s),
        "--stderr", str(job.workdir / "cekirdek.err"),
        "--olaylar", str(job.workdir / "olaylar.jsonl"),
        "--gorev", task,
    ]  # fmt: skip
    if job.area.needs_chrome:
        komut += ["--chrome", str(job.workdir / "chrome.json"),
                  "--eslestirme-suresi", str(CHROME_PAIRING_S)]  # fmt: skip
    return komut


async def _drive(job: Job, root: Path, task: str, options: RunnerOptions) -> dict[str, object]:
    ortam = {"FUSION_CONFIG": str(options.config)} if options.config else {}
    surec = await asyncio.create_subprocess_exec(
        *_driver_command(job, root, task),
        cwd=_REPO_ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**_inherited_env(), **ortam},
    )
    try:
        cikti, hata = await asyncio.wait_for(
            surec.communicate(), timeout=job.area.timeout_s + DRIVER_GRACE_S
        )
    except TimeoutError:
        surec.kill()
        await surec.wait()
        return {"hata": "sürücü zaman aşımı"}
    await asyncio.to_thread((job.workdir / "surucu.json").write_bytes, cikti)
    try:
        return dict(json.loads(cikti))
    except ValueError:
        return {"hata": (hata.decode(errors="replace") or "sürücü çıktısı yok")[-800:]}


def _inherited_env() -> dict[str, str]:
    return dict(os.environ)


def metrics_from(driver: Mapping[str, object]) -> RunMetrics:
    """Sürücünün sayaçlarından koşu ölçülerini çıkar."""
    sayac = driver.get("sayaclar")
    sayaclar = sayac if isinstance(sayac, dict) else {}
    araclar = driver.get("araclar")
    turlar = driver.get("turlar")
    ilk_tur = turlar[0] if isinstance(turlar, list) and turlar else {}
    return RunMetrics(
        elapsed_s=float(ilk_tur.get("sure_sn", 0.0)) if isinstance(ilk_tur, dict) else 0.0,
        model_calls=int(sayaclar.get("model_cagrisi", 0)),
        web_model_calls=int(sayaclar.get("web_model_cagrisi", 0)),
        teacher_calls=int(sayaclar.get("ogretmen_cagrisi", 0)),
        tool_calls=len(araclar) if isinstance(araclar, list) else 0,
        tool_errors=int(sayaclar.get("arac_hatasi", 0)),
        fallbacks=int(sayaclar.get("yedege_gecis", 0)),
        prompt_tokens=int(sayaclar.get("istem_token", 0)),
        max_prompt_tokens=int(sayaclar.get("en_buyuk_istem", 0)),
    )


def _agent_summary(driver: Mapping[str, object]) -> tuple[bool | None, str]:
    turlar = driver.get("turlar")
    if not isinstance(turlar, list) or not turlar or not isinstance(turlar[0], dict):
        return None, ""
    ok = turlar[0].get("ok")
    return (bool(ok) if ok is not None else None), str(turlar[0].get("metin", ""))


async def run_job(job: Job, options: RunnerOptions, chrome_lock: asyncio.Lock) -> RunRecord:
    """Tek koşu: hazırla → ajanı sür → denetle → sınıflandır."""
    job.workdir.mkdir(parents=True, exist_ok=True)
    with ExitStack() as yigin:
        degerler: dict[str, str] = {}
        if job.area.prepare is not None:
            degerler.update(yigin.enter_context(job.area.prepare(job.workdir)))
        kok = Path(degerler[job.area.root_key]) if job.area.root_key else job.workdir
        gorev = job.area.task.format_map(degerler) if degerler else job.area.task
        if job.area.needs_chrome:
            async with chrome_lock:
                surucu = await _drive(job, kok, gorev, options)
        else:
            surucu = await _drive(job, kok, gorev, options)
        ok, metin = _agent_summary(surucu)
        surucu_hatasi = str(surucu.get("hata", ""))
        denetim = await asyncio.to_thread(
            _safe_inspect, job.area, job.workdir, {**degerler, "agent_text": metin}
        )
    olculer = metrics_from(surucu)
    araclar = surucu.get("araclar")
    return RunRecord(
        area=job.area.name,
        attempt=job.attempt,
        workdir=str(job.workdir),
        outcome=classify(denetim, olculer, surucu_hatasi),
        inspection=denetim,
        metrics=olculer,
        agent_ok=ok,
        agent_text=metin[:2000],
        driver_error=surucu_hatasi,
        tools=tuple(str(ad) for ad in araclar) if isinstance(araclar, list) else (),
    )


def _safe_inspect(area: Area, workdir: Path, values: Mapping[str, str]) -> Inspection:
    """Denetçinin kendi hatası koşuyu düşürmez, geçersiz kılar (sınır katmanı)."""
    try:
        return area.inspect(workdir, values)
    except Exception as hata:  # sınır: denetçi hatası ölçüm hatasıdır, koşu geçersiz sayılır
        _LOG.exception("denetçi çöktü", extra={"alan": area.name, "klasor": str(workdir)})
        return Inspection(invalid_reason=f"denetçi hatası: {type(hata).__name__}: {hata}"[:500])


async def run_all(jobs: Sequence[Job], options: RunnerOptions) -> list[RunRecord]:
    """İşleri en çok `parallel` eşzamanlı, `stagger_s` arayla başlatarak koş."""
    sinir = asyncio.Semaphore(options.parallel)
    chrome_kilidi = asyncio.Lock()

    async def _tek(sira: int, job: Job) -> RunRecord:
        await asyncio.sleep(sira * options.stagger_s if sira < options.parallel else 0)
        async with sinir:
            return await run_job(job, options, chrome_kilidi)

    return list(await asyncio.gather(*(_tek(sira, job) for sira, job in enumerate(jobs))))
