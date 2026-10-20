"""Hafıza, sohbet geçmişi ve proje taşıma için uçtan uca canlı kabul.

Arayüzün kullandığı aynı çekirdek isteklerini (`bellek.*`, `sohbet.*`,
`tur.calistir`) gerçek `fusion app` süreçleriyle sırasıyla çalıştırır:

1. Bir sekmede kişisel hafızaya test bilgisi eklenir.
2. AYRI bir süreçte (yeni sekme, yeni sohbet) modele sorulur; cevap hafızadaki
   bilgiyi içermeli.
3. Sohbet kendi proje kökünde listelenmeli, başka köke taşınabilmeli ve silinebilmeli.
4. Test hafızası silinir; kullanıcının gerçek hafızasında iz kalmaz.

Kullanım:  python -m evals.e2e_features
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any

#: Test hafızası; kullanıcının gerçek anılarıyla karışmasın diye işaretli.
TEST_ANISI = "E2E-FUSION-DENEME: Kullanıcının kedisinin adı Pamukgöz."
BEKLENEN = "Pamukgöz"


class AppClient:
    """`fusion app` sürecini protokolle süren küçük istemci."""

    def __init__(self, kok: Path, sohbet_id: str) -> None:
        self.kok, self.sohbet_id = kok, sohbet_id
        self._bekleyen: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._sayac = 0

    async def __aenter__(self) -> AppClient:
        self._surec = await asyncio.create_subprocess_exec(
            str(Path(sys.executable).with_name("fusion")),
            "app",
            cwd=self.kok,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=16 * 1024 * 1024,
        )
        self._okuyucu = asyncio.create_task(self._oku())
        await self.istek(
            "oturum.baslat", {"kok": str(self.kok), "sohbet_id": self.sohbet_id, "mod": "auto"}
        )
        return self

    async def __aexit__(
        self, *_: type[BaseException] | BaseException | TracebackType | None
    ) -> None:
        self._okuyucu.cancel()
        assert self._surec.stdin is not None
        self._surec.stdin.close()
        try:
            await asyncio.wait_for(self._surec.wait(), timeout=20)
        except TimeoutError:
            self._surec.kill()

    async def _oku(self) -> None:
        assert self._surec.stdout is not None
        while line := await self._surec.stdout.readline():
            try:
                mesaj = json.loads(line)
            except ValueError:
                continue
            if mesaj.get("tip") == "soru":
                # Bu senaryoda izin istenmemeli; istenirse reddet ve kaydet.
                self._yaz({"tip": "cevap", "id": mesaj["id"], "veri": {"secim": "deny"}})
            elif mesaj.get("tip") == "sonuc" and mesaj.get("id") in self._bekleyen:
                self._bekleyen.pop(mesaj["id"]).set_result(mesaj.get("veri") or {})

    def _yaz(self, payload: dict[str, Any]) -> None:
        assert self._surec.stdin is not None
        self._surec.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())

    async def istek(self, ad: str, veri: dict[str, Any], sure: float = 120) -> dict[str, Any]:
        self._sayac += 1
        kimlik = f"{ad}-{self._sayac}"
        self._bekleyen[kimlik] = asyncio.get_running_loop().create_future()
        self._yaz({"tip": "istek", "id": kimlik, "ad": ad, "veri": veri})
        return await asyncio.wait_for(self._bekleyen[kimlik], timeout=sure)


async def calistir() -> dict[str, Any]:
    kayit: dict[str, Any] = {}
    temel = Path(tempfile.mkdtemp(prefix="fusion-e2e-"))
    kok_a, kok_b = temel / "proje-a", temel / "proje-b"
    kok_a.mkdir()
    kok_b.mkdir()

    async with AppClient(kok_a, str(uuid.uuid4())) as sekme1:
        eklenen = await sekme1.istek("bellek.ekle", {"metin": TEST_ANISI})
        liste = await sekme1.istek("bellek.listele", {})
        kayit["hafiza_eklendi"] = bool(eklenen.get("ok")) and TEST_ANISI in json.dumps(
            liste, ensure_ascii=False
        )
        ani_id = eklenen.get("id")

    sohbet_id = str(uuid.uuid4())
    async with AppClient(kok_a, sohbet_id) as sekme2:
        basla = time.monotonic()
        cevap = await sekme2.istek(
            "tur.calistir", {"gorev": "Kedimin adı ne? Yalnız adı yaz."}, sure=600
        )
        kayit["tur_sn"] = round(time.monotonic() - basla, 1)
        kayit["cevap"] = str(cevap.get("metin", ""))[:300]
        kayit["hafiza_kullanildi"] = BEKLENEN.lower() in kayit["cevap"].lower()
        liste_a = await sekme2.istek("sohbet.listele", {})
        kayit["sohbet_listede"] = sohbet_id in json.dumps(liste_a)

    # Açık sohbet taşınamaz (çekirdek "önce kapat" der); arayüz de taşımayı
    # başka bir oturumdan yapar. Sohbet kapandıktan sonra hedef köktekinden taşı.
    async with AppClient(kok_b, str(uuid.uuid4())) as sekme3:
        tasima = await sekme3.istek(
            "sohbet.tasi",
            {"sohbet_id": sohbet_id, "kaynak_kok": str(kok_a), "hedef_kok": str(kok_b)},
        )
        kayit["tasindi"] = bool(tasima.get("ok"))
        liste_b = await sekme3.istek("sohbet.listele", {})
        kayit["hedefte_gorunuyor"] = sohbet_id in json.dumps(liste_b)
        silme = await sekme3.istek("sohbet.sil", {"sohbet_id": sohbet_id, "kok": str(kok_b)})
        liste_b2 = await sekme3.istek("sohbet.listele", {})
        kayit["silindi"] = bool(silme.get("ok")) and sohbet_id not in json.dumps(liste_b2)
        if ani_id is not None:
            await sekme3.istek("bellek.sil", {"id": ani_id})
        liste = await sekme3.istek("bellek.listele", {})
        kayit["hafiza_temizlendi"] = TEST_ANISI not in json.dumps(liste, ensure_ascii=False)

    kayit["gecti"] = all(
        kayit[anahtar]
        for anahtar in (
            "hafiza_eklendi",
            "hafiza_kullanildi",
            "sohbet_listede",
            "tasindi",
            "hedefte_gorunuyor",
            "silindi",
            "hafiza_temizlendi",
        )
    )
    return kayit


def main() -> None:
    print(json.dumps(asyncio.run(calistir()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
