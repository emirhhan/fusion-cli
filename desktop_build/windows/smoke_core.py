"""Windows'ta çekirdeği (`fusion app`) masaüstü uygulamasının açılış istekleriyle dener.

Neden var — ölçüldü (28 Eylül): Windows'ta uygulama "Çekirdek bağlantısı kapatıldı"
dedi; çekirdeğin hata çıktısı atıldığı için sebep görünmüyordu ve Windows derlemesi
çekirdeği hiç çalıştırmıyordu. Bu betik çekirdeği başlatır, açılış isteklerini
gönderir; çekirdek kapanırsa hata çıktısını basıp başarısız olur.

Kullanım: python smoke_core.py <çekirdek komutu...>
Örnek:    python smoke_core.py fusion app
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time

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


def main(komut: list[str]) -> int:
    with tempfile.TemporaryDirectory() as kok:
        surec = subprocess.Popen(
            komut,
            cwd=kok,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        assert surec.stdin and surec.stdout
        for sira, ad in enumerate(ISTEKLER, start=1):
            satir = json.dumps({"tip": "istek", "id": str(sira), "ad": ad, "veri": {}})
            try:
                surec.stdin.write(satir + "\n")
                surec.stdin.flush()
            except OSError:
                return _coktu(surec, ad)
            if not _cevabi_bekle(surec, str(sira)):
                return _coktu(surec, ad)
            print(f"tamam: {ad}", flush=True)
        surec.stdin.close()
        surec.wait(timeout=30)
    print("çekirdek tüm açılış isteklerini cevapladı")
    return 0


def _cevabi_bekle(surec: subprocess.Popen[str], kimlik: str) -> bool:
    assert surec.stdout
    bitis = time.monotonic() + CEVAP_SURESI_S
    while time.monotonic() < bitis:
        satir = surec.stdout.readline()
        if not satir:
            return False
        try:
            veri = json.loads(satir)
        except json.JSONDecodeError:
            print(f"çözülemeyen satır: {satir[:200]!r}")
            continue
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return True
    return False


def _coktu(surec: subprocess.Popen[str], ad: str) -> int:
    try:
        _, hata = surec.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        surec.kill()
        _, hata = surec.communicate()
    print(f"ÇEKİRDEK '{ad}' isteğinde kapandı (çıkış kodu {surec.returncode})")
    print("---- çekirdek hata çıktısı ----")
    print(hata[-8000:] if hata else "(boş)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
