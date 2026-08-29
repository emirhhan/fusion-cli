"""Paketlenmiş ikilinin gerçekten çalıştığını doğrulayan duman testi.

Model çağrısı YAPMAZ: yalnız `runtime-health --json` sözleşmesini ve
`app` stdio protokolünün oturum durumunu (`oturum.durum`) sınar.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import select
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

_TIMEOUT_SANIYE = 30
#: Şifreli credential deposunun anahtarı boşsa oturum açılışı sistem
#: anahtarlığına (macOS Keychain) dokunur; başsız/etkileşimsiz bir ortamda bu
#: erişim süresiz asılı kalabilir. Duman testi gerçek sırra dokunmaz — yalnız
#: bu tek süreç için rastgele, tek kullanımlık bir değer üretip anahtarlık
#: yolunu devre dışı bırakır.
_DUMMY_SECRET_ENV = {"FUSION_SECRET_KEY": secrets.token_urlsafe(32)}


def _request(
    process: subprocess.Popen[str], request_id: str, name: str, data: dict[str, object]
) -> dict[str, Any]:
    assert process.stdin is not None and process.stdout is not None
    request = {"tip": "istek", "id": request_id, "ad": name, "veri": data}
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    while True:
        readable, _, _ = select.select([process.stdout], [], [], _TIMEOUT_SANIYE)
        assert readable, f"{name} isteği 30 saniyede yanıt vermedi"
        response = json.loads(process.stdout.readline())
        if response.get("tip") == "sonuc" and response.get("id") == request_id:
            return cast(dict[str, Any], response.get("veri", {}))


def _workspace_smoke(executable: Path, env: dict[str, str]) -> None:
    """Paketli protokolün gerçek proje araçlarını boş HOME ile sınar."""
    with tempfile.TemporaryDirectory(prefix="fusion-runtime-smoke-") as raw:
        root = Path(raw) / "project-one"
        other = Path(raw) / "project-two"
        home = Path(raw) / "home"
        root.mkdir()
        other.mkdir()
        home.mkdir()
        (root / "hello.txt").write_text("Fusion hazır\n", encoding="utf-8")
        (root / "pixel.png").write_bytes(b"\x89PNG\r\n\x1a\ncontent")
        (other / "second.txt").write_text("ikinci oturum\n", encoding="utf-8")
        process = subprocess.Popen(
            [str(executable), "app"],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**env, "HOME": str(home)},
        )
        listing = _request(process, "files", "proje.listele", {"yol": ""})
        assert listing["ok"] is True and any(
            entry["ad"] == "hello.txt" for entry in listing["girdiler"]
        )
        read = _request(process, "read", "proje.oku", {"yol": "hello.txt"})
        assert read["icerik"] == "Fusion hazır\n"
        preview = _request(process, "preview", "proje.onizle", {"yol": "pixel.png"})
        assert preview["ok"] is True and preview["tur"] == "image"

        started = _request(process, "start", "surec.baslat", {"komut": "sleep 30"})
        process_id = started["surec_id"]
        processes = _request(process, "list", "surec.listele", {})
        assert any(item["surec_id"] == process_id for item in processes["surecler"])
        stopped = _request(process, "stop", "surec.kes", {"surec_id": process_id})
        assert stopped["ok"] is True

        switched = _request(process, "switch", "oturum.baslat", {"kok": str(other)})
        assert switched["kok"] == str(other)
        second = _request(process, "second", "proje.listele", {"yol": ""})
        assert [entry["ad"] for entry in second["girdiler"]] == ["second.txt"]

        capabilities = _request(process, "capabilities", "yetenek.katalog", {})
        assert capabilities["ok"] is True
        control = _request(process, "control", "kontrol.durum", {})
        assert control["ok"] is True and control["gateway"]["durum"] == "kapali"
        # Kontrol sözleşmesi sır değerlerini asla paketli süreçten dışarı çıkarmaz.
        assert _DUMMY_SECRET_ENV["FUSION_SECRET_KEY"] not in json.dumps(control)

        # Dersler paketli ikilide de çalışmalı: ekran bu iki isteğin üstünde duruyor.
        lessons = _request(process, "lessons", "ders.listele", {})
        assert lessons["ok"] is True and len(lessons["dersler"]) == 8
        lesson = _request(process, "lesson", "ders.getir", {"id": lessons["dersler"][0]["id"]})
        assert lesson["ok"] is True and lesson["adimlar"]
        # Ders adımı yürütülebilir komut taşımaz; paketli sürümde de taşımamalı.
        for step in lesson["adimlar"]:
            assert step["eylem"]["tur"] in ("composer", "sekme")

        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=_TIMEOUT_SANIYE) == 0


def smoke(executable: Path) -> None:
    """Paketlenmiş ikiliyi çalıştırıp sağlık ve stdio protokolünü doğrular."""
    env = {**os.environ, **_DUMMY_SECRET_ENV}
    health = subprocess.run(
        [str(executable), "runtime-health", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SANIYE,
        env=env,
    )
    assert json.loads(health.stdout)["ok"] is True

    process = subprocess.Popen(
        [str(executable), "app"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    response = _request(process, "smoke-1", "oturum.durum", {})
    assert response.get("ok") is True
    assert process.stdin is not None
    process.stdin.close()
    assert process.wait(timeout=_TIMEOUT_SANIYE) == 0
    _workspace_smoke(executable, env)


def main() -> None:
    """CLI girişi: verilen ikili yolunu duman testinden geçirir."""
    parser = argparse.ArgumentParser(description="Paketlenmiş Fusion ikilisini sınar.")
    parser.add_argument("executable", type=Path, help="Paketlenmiş `fusion` ikilisinin yolu")
    args = parser.parse_args()

    smoke(args.executable.resolve())
    print(
        "Duman testi geçti: sağlık, proje, süreç, oturum, katalog, kontrol, "
        "önizleme ve ders protokolleri doğrulandı."
    )


if __name__ == "__main__":
    main()
