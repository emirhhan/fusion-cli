"""Windows'ta çekirdeği (`fusion app`) masaüstü uygulamasının açılış istekleriyle dener.

Neden var — ölçüldü (28 Eylül): Windows'ta uygulama "Çekirdek bağlantısı kapatıldı"
dedi; çekirdeğin hata çıktısı atıldığı için sebep görünmüyordu ve Windows derlemesi
çekirdeği hiç çalıştırmıyordu. Bu betik çekirdeği başlatır, açılış isteklerini
gönderir; çekirdek kapanır ya da takılırsa hata çıktısını basıp başarısız olur.

Betik HİÇBİR koşulda takılmaz: çıktı ayrı bir iş parçacığında okunur, her cevap
için süre sınırı vardır, hata çıktısı dosyaya yazılır (çekirdeğin alt süreçleri
boruyu açık tutsa bile okunabilir) ve sonunda süreç ağacının tamamı kapatılır.

Kullanım: python smoke_core.py <çekirdek komutu...>
Örnek:    python smoke_core.py fusion app
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ISTEKLER = (
    "oturum.baslat",
    "kontrol.durum",
    "oturum.durum",
    "kullanim.durum",
    "proje.listele",
    "gecmis.oturumlar",
    "yetenek.katalog",
    "ses.durum",
)
#: Tek bir isteğin cevabı için beklenecek süre (sn). İlk istek modülleri yükler.
CEVAP_SURESI_S = 120.0


def yaz(metin: str) -> None:
    print(metin, flush=True)


def main(komut: list[str]) -> int:
    with tempfile.TemporaryDirectory() as kok:
        hata_dosyasi = Path(kok) / "cekirdek-stderr.log"
        with hata_dosyasi.open("w", encoding="utf-8") as hata:
            surec = subprocess.Popen(
                komut,
                cwd=kok,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=hata,
                text=True,
                encoding="utf-8",
            )
        satirlar: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=_oku, args=(surec, satirlar), daemon=True).start()
        try:
            for sira, ad in enumerate(ISTEKLER, start=1):
                if not _gonder(surec, sira, ad) or not _bekle(satirlar, str(sira)):
                    _kapat(surec)
                    yaz(f"ÇEKİRDEK '{ad}' isteğinde cevap vermedi (çıkış kodu {surec.returncode})")
                    _hata_bas(hata_dosyasi)
                    return 1
                yaz(f"tamam: {ad}")
        finally:
            _kapat(surec)
    yaz("çekirdek tüm açılış isteklerini cevapladı")
    return 0


def _oku(surec: subprocess.Popen[str], satirlar: queue.Queue[str | None]) -> None:
    assert surec.stdout
    for satir in surec.stdout:
        satirlar.put(satir)
    satirlar.put(None)


def _gonder(surec: subprocess.Popen[str], sira: int, ad: str) -> bool:
    assert surec.stdin
    satir = json.dumps({"tip": "istek", "id": str(sira), "ad": ad, "veri": {}})
    try:
        surec.stdin.write(satir + "\n")
        surec.stdin.flush()
    except OSError:
        return False
    return True


def _bekle(satirlar: queue.Queue[str | None], kimlik: str) -> bool:
    import time

    bitis = time.monotonic() + CEVAP_SURESI_S
    while (kalan := bitis - time.monotonic()) > 0:
        try:
            satir = satirlar.get(timeout=kalan)
        except queue.Empty:
            return False
        if satir is None:
            return False
        try:
            veri = json.loads(satir)
        except json.JSONDecodeError:
            yaz(f"çözülemeyen satır: {satir[:200]!r}")
            continue
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return True
    return False


def _kapat(surec: subprocess.Popen[str]) -> None:
    if surec.poll() is not None:
        return
    if sys.platform == "win32":
        # Alt süreçler de kapanmalı; yoksa boru açık kalır ve iş takılır.
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(surec.pid)],
            capture_output=True,
            check=False,
        )
    else:
        surec.kill()
    try:
        surec.wait(timeout=30)
    except subprocess.TimeoutExpired:
        yaz("çekirdek kapatılamadı")


def _hata_bas(dosya: Path) -> None:
    metin = dosya.read_text(encoding="utf-8", errors="replace") if dosya.exists() else ""
    yaz("---- çekirdek hata çıktısı ----")
    yaz(metin[-12000:] if metin.strip() else "(boş)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
