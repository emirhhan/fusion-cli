"""Paketlenmiş ikilinin gerçekten çalıştığını doğrulayan duman testi.

Model çağrısı YAPMAZ: yalnız `runtime-health --json` sözleşmesini ve
`app` stdio protokolünün oturum durumunu (`oturum.durum`) sınar.
"""

from __future__ import annotations

import argparse
import json
import select
import subprocess
from pathlib import Path

_TIMEOUT_SANIYE = 30


def smoke(executable: Path) -> None:
    """Paketlenmiş ikiliyi çalıştırıp sağlık ve stdio protokolünü doğrular."""
    health = subprocess.run(
        [str(executable), "runtime-health", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SANIYE,
    )
    assert json.loads(health.stdout)["ok"] is True

    process = subprocess.Popen(
        [str(executable), "app"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    request = {"tip": "istek", "id": "smoke-1", "ad": "oturum.durum", "veri": {}}
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    readable, _, _ = select.select([process.stdout], [], [], _TIMEOUT_SANIYE)
    assert readable, "app protokolü 30 saniyede yanıt vermedi"
    response = json.loads(process.stdout.readline())
    assert response.get("tip") == "sonuc" and response.get("id") == "smoke-1"
    process.stdin.close()
    assert process.wait(timeout=_TIMEOUT_SANIYE) == 0


def main() -> None:
    """CLI girişi: verilen ikili yolunu duman testinden geçirir."""
    parser = argparse.ArgumentParser(description="Paketlenmiş Fusion ikilisini sınar.")
    parser.add_argument("executable", type=Path, help="Paketlenmiş `fusion` ikilisinin yolu")
    args = parser.parse_args()

    smoke(args.executable.resolve())
    print("Duman testi geçti: sağlık ve app protokolü doğrulandı.")


if __name__ == "__main__":
    main()
