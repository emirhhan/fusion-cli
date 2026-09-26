"""Uzun, çok dosyalı kodlama görevlerinin gizli testli canlı kabulü.

Her görev klasöründe:
- `proje/`   ajanın çalışacağı fikstür (geçici bir kopyaya alınır),
- `gorev.txt` ajana verilen görev,
- `gizli/`   ajanın GÖRMEDİĞİ kabul testleri (olumlu işlev + olumsuz güvenlik/atomiklik).

Ajan bittikten sonra gizli testler çalışma alanına kopyalanıp koşulur. Ajanın
`ok=True` demesi ile gizli testlerin geçmesi ayrı ölçülür: ikisi ayrışırsa
`sahte_basari` işaretlenir (bkz. `evals/acceptance.py` eşiği: sıfır).

Kullanım:
    python -m evals.long_tasks.run fiyat_aktarimi [--tekrar 2] [--sure 1800]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parent


def _gizli_testleri_kos(calisma: Path, gorev: Path) -> dict[str, Any]:
    hedef = calisma / "_gizli_kabul"
    shutil.rmtree(hedef, ignore_errors=True)
    shutil.copytree(gorev / "gizli", hedef)
    sonuc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(hedef)],
        cwd=calisma,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PYTHONPATH": str(calisma), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    ozet = sonuc.stdout.strip().splitlines()[-1] if sonuc.stdout.strip() else sonuc.stderr[-300:]
    gecen = int(m.group(1)) if (m := re.search(r"(\d+) passed", ozet)) else 0
    kalan = int(m.group(1)) if (m := re.search(r"(\d+) (?:failed|error)", ozet)) else 0
    return {"gecti": sonuc.returncode == 0, "gecen": gecen, "dusen": kalan, "ozet": ozet}


def _ajan(calisma: Path, gorev_metni: str, sure: float, stderr: Path) -> dict[str, Any]:
    komut = [
        sys.executable, "-m", "evals.live_drive",
        "--kok", str(calisma), "--mod", "auto", "--sure", str(sure),
        "--stderr", str(stderr), "--gorev", gorev_metni,
    ]  # fmt: skip
    cikti = subprocess.run(
        komut, capture_output=True, text=True, cwd=KOK.parent.parent, check=False
    )
    try:
        return dict(json.loads(cikti.stdout))
    except ValueError:
        return {"hata": cikti.stderr[-1000:]}


def kos(ad: str, sure: float) -> dict[str, Any]:
    gorev = KOK / ad
    calisma = Path(tempfile.mkdtemp(prefix=f"uzun-{ad}-"))
    shutil.copytree(gorev / "proje", calisma, dirs_exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=calisma, check=False)
    subprocess.run(["git", "add", "-A"], cwd=calisma, check=False)
    subprocess.run(
        ["git", "-c", "user.email=e@x", "-c", "user.name=e", "commit", "-qm", "baslangic"],
        cwd=calisma,
        check=False,
    )
    basla = time.monotonic()
    ajan = _ajan(
        calisma,
        (gorev / "gorev.txt").read_text(encoding="utf-8"),
        sure,
        calisma.with_suffix(".err"),
    )
    gizli = _gizli_testleri_kos(calisma, gorev)
    degisen = subprocess.run(
        ["git", "status", "--short"], cwd=calisma, capture_output=True, text=True, check=False
    ).stdout.split("\n")
    tur = (ajan.get("turlar") or [{}])[0]
    return {
        "gorev": ad,
        "calisma": str(calisma),
        "sure_sn": round(time.monotonic() - basla, 1),
        "ajan_ok": tur.get("ok"),
        "gizli": gizli,
        "sahte_basari": bool(tur.get("ok")) and not gizli["gecti"],
        "izin_sayisi": len(ajan.get("izinler", [])),
        "sorular": ajan.get("sorular", []),
        "arac_sayisi": len(ajan.get("araclar", [])),
        "degisen_dosyalar": [s for s in degisen if s.strip() and "_gizli_kabul" not in s],
        "ajan_metni": str(tur.get("metin", ""))[:1500],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gorevler", nargs="+")
    parser.add_argument("--tekrar", type=int, default=1)
    parser.add_argument("--sure", type=float, default=1800)
    args = parser.parse_args()
    sonuclar = [kos(ad, args.sure) for ad in args.gorevler for _ in range(args.tekrar)]
    print(json.dumps(sonuclar, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
