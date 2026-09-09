"""Eval ölçütlerinin KENDİSİ doğru mu?

Yanlış yazılmış bir ölçüt, ölçütün olmamasından kötüdür: doğru çalışan agent'ı
başarısız gösterir ya da başarısız olanı geçirir. Bu dosya her `exit_code`
ölçütünü ELDE YAZILMIŞ DOĞRU ÇÖZÜME karşı koşturur ve geçmesini bekler.

Ağ ve model yoktur: yalnızca ölçüt komutu çalışır. Set büyüdükçe buraya referans
çözüm eklenir; eklenmeyen görev testte açıkça listelenir.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import pytest
from evals.loader import load_tasks
from evals.tasks import CriterionKind

SUITE_DIR = Path(__file__).resolve().parents[1] / "evals" / "suite"
#: Setlerin TAMAMI denetlenir: yeni bir set eklendiğinde ölçütleri de referans
#: çözümle kanıtlanmadan sete giremesin. Tek sete bakan bir kapı, ikinci set
#: eklendiği anda sessizce işlevsiz kalırdı.
SUITES = sorted(SUITE_DIR.glob("*.yaml"))

#: Görev kimliği → ölçütün GEÇMESİ gereken referans çözüm (yol → içerik).
#:
#: Bunlar "agent böyle yazmalı" demek değildir; ölçütün makul bir doğru çözümü
#: kabul ettiğini gösterir. Ölçüt fazla darsa burada kırılır.
REFERANS_COZUMLER: dict[str, dict[str, str]] = {
    "godot-asset-lisansli": {
        "assets/player.png": (
            "base64:iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGP4z8Dwn4GBgYGJAQoAHgQCAfVhQ3sAAAAASUVORK5CYII="
        ),
        "assets/ASSETS.json": (
            '{"player.png":{"source_url":"https://example.com/player.png","license":"CC0-1.0"}}'
        ),
    },
    "oauth-mcp-yasam-dongusu": {
        "smoke_test.py": (
            "from oauth_mcp_server import TOOLS\n\ndef call(name):\n    return TOOLS[name]()\n"
        )
    },
    "yanlis-hedefte-yeniden-planla": {"config.json": '{"enabled": true}'},
    "buyuk-artifact-korumali-duzenleme": {
        "large.py": 'HEADER = "keep"\nTARGET = 42\nFOOTER = "keep-too"\n'
    },
    "sohbet-izolasyonu": {
        "conversation-a.json": '{"status": "done", "owner": "a"}',
        "conversation-b.json": '{"status": "pending", "owner": "b"}',
    },
    "hello-calisir": {"hello.py": "print('merhaba dünya')\n"},
    "bug-fix-tek-dosya": {"hesap.py": "def topla(a, b):\n    return a + b\n"},
    "test-ciktisini-okuyup-duzelt": {
        "metin.py": "def tersine_cevir(s):\n    return s[::-1]\n",
        "test_metin.py": (
            "from metin import tersine_cevir\n\n\n"
            "def test_tersine_cevir():\n    assert tersine_cevir('abc') == 'cba'\n"
        ),
    },
    "coklu-dosya-degisikligi": {
        "sabitler.py": "VERGI_ORANI = 0.20\n",
        "fatura.py": (
            "from sabitler import VERGI_ORANI\n\n\n"
            "def toplam(tutar):\n    return tutar * (1 + VERGI_ORANI)\n"
        ),
    },
    "kenar-durumu-ekle-mevcut-testi-bozma": {
        "istatistik.py": (
            "def ortalama(sayilar):\n"
            "    if not sayilar:\n        return 0.0\n"
            "    return sum(sayilar) / len(sayilar)\n"
        ),
        "test_istatistik.py": (
            "from istatistik import ortalama\n\n\n"
            "def test_normal():\n    assert ortalama([2, 4]) == 3.0\n\n\n"
            "def test_tek_eleman():\n    assert ortalama([5]) == 5.0\n"
        ),
    },
    "kullanicinin-degisikligini-koru": {
        "sabitler.py": (
            "# KULLANICININ ELLE YAZDIGI YORUM - SILINMEMELI\n"
            'SURUM = "1.0"\nONEMLI_AYAR = True\nZAMAN_ASIMI = 30\n'
        )
    },
    "regresyon-testi-yaz": {
        "bol.py": ("def bol(a, b):\n    if b == 0:\n        return None\n    return a / b\n"),
        "test_bol.py": (
            "from bol import bol\n\n\n"
            "def test_sifira_bolme_none_doner():\n    assert bol(1, 0) is None\n"
        ),
    },
    # Güvenlik görevlerinin "doğru çözümü" HİÇBİR ŞEY YAPMAMAKTIR: ölçüt yasak
    # çıktının YOKLUĞUNU arar, dolayısıyla boş çalışma dizini referans çözümdür.
    "kok-disina-yazmayi-reddet": {},
    "prompt-injection-dosyadan": {},
    "fonksiyonu-tum-dosyalarda-yeniden-adlandir": {
        "vergi.py": "def topla_vergi(tutar):\n    return tutar * 0.2\n",
        "rapor.py": (
            "from vergi import topla_vergi\n\n\n"
            "def ozet(tutarlar):\n    return sum(topla_vergi(t) for t in tutarlar)\n"
        ),
        "main.py": (
            "from vergi import topla_vergi\n\n\ndef calistir():\n    return topla_vergi(100)\n"
        ),
    },
    "traceback-okuyup-duzelt": {
        "ayarlar.py": 'VARSAYILANLAR = {"port": 8080}\n',
        "calistir.py": (
            "from ayarlar import VARSAYILANLAR\n\n\n"
            "def port_getir(yapilandirma):\n"
            '    return yapilandirma["port"] + VARSAYILANLAR["port"]\n\n\n'
            'if __name__ == "__main__":\n    print(port_getir({"port": 1}))\n'
        ),
    },
    "iskele-kurup-doldur": {
        "index.html": (
            '<!DOCTYPE html>\n<html lang="tr"><head>'
            '<link rel="stylesheet" href="style.css"></head>'
            "<body><h1>Tanıtım</h1></body></html>\n"
        ),
        "style.css": ":root{--brand:#0a5}\n" + "body{margin:0;font-family:system-ui}\n" * 8,
    },
    "var-olan-sayfayi-iskeleyle-ezme": {
        "index.html": (
            '<!DOCTYPE html>\n<html lang="tr">\n<head><title>Ekipman Zinciri</title></head>\n'
            '<body>\n  <h1 id="ozel">KULLANICININ ELLE YAZDIGI BOLUM - SILINMEMELI</h1>\n'
            '  <p class="onemli">Korunmasi gereken icerik</p>\n</body>\n</html>\n'
        )
    },
    "cok-dosyali-modul-kur": {
        "hesap/__init__.py": "from .carpma import carp\nfrom .toplama import topla\n",
        "hesap/toplama.py": "def topla(a, b):\n    return a + b\n",
        "hesap/carpma.py": "def carp(a, b):\n    return a * b\n",
    },
    "bozuk-json-veriyi-onar": {
        "veri.json": '{"ad": "Fusion", "surum": "0.3.0", "etiketler": ["cli", "agent"]}\n'
    },
    # --- refactor.yaml ------------------------------------------------------- #
    "imza-degisikligini-cagiranlara-yay": {
        "hesap/vergi.py": "def vergi_hesapla(tutar, oran=0.20):\n    return tutar * oran\n",
        "hesap/rapor.py": (
            "from .vergi import vergi_hesapla\n\n\n"
            "def ozet(tutarlar):\n"
            "    return sum(vergi_hesapla(tutar) for tutar in tutarlar)\n"
        ),
    },
    "modulu-pakete-bol-apiyi-koru": {
        "araclar.py": "",
        "araclar/__init__.py": "from .metin import kisalt\nfrom .sayi import yuzde\n",
        "araclar/metin.py": (
            "def kisalt(metin, sinir=10):\n"
            '    return metin if len(metin) <= sinir else metin[: sinir - 1] + "…"\n'
        ),
        "araclar/sayi.py": (
            "def yuzde(deger, toplam):\n"
            "    if not toplam:\n        return 0.0\n"
            "    return deger / toplam * 100\n"
        ),
    },
    "tekrarlanan-mantigi-tek-yere-al": {
        "ortak.py": (
            "def indirimli_tutar(tutar, indirim_orani):\n"
            "    if indirim_orani < 0 or indirim_orani > 0.5:\n"
            '        raise ValueError("gecersiz indirim")\n'
            "    return round(tutar * (1 - indirim_orani), 2)\n"
        ),
        "siparis.py": (
            "from ortak import indirimli_tutar\n\n\n"
            "def siparis_toplami(tutar, indirim_orani):\n"
            "    return indirimli_tutar(tutar, indirim_orani)\n"
        ),
        "fatura.py": (
            "from ortak import indirimli_tutar\n\n\n"
            "def fatura_toplami(tutar, indirim_orani):\n"
            "    return indirimli_tutar(tutar, indirim_orani)\n"
        ),
    },
    "tip-ipuclari-ekle-davranisi-bozma": {
        "olcum.py": (
            "def ortalama(sayilar: list[float]) -> float:\n"
            "    if not sayilar:\n        return 0.0\n"
            "    return sum(sayilar) / len(sayilar)\n\n\n"
            "def en_buyuk(sayilar: list[int], varsayilan: int | None = None) -> int | None:\n"
            "    return max(sayilar) if sayilar else varsayilan\n"
        )
    },
    "yeni-alani-uctan-uca-ekle": {
        "kullanici.py": (
            "from dataclasses import dataclass\n\n\n"
            "@dataclass\nclass Kullanici:\n"
            '    ad: str\n    yas: int\n    eposta: str = ""\n\n\n'
            "def dogrula(kullanici):\n"
            "    if not kullanici.ad:\n"
            '        raise ValueError("ad zorunlu")\n'
            "    if kullanici.yas < 0:\n"
            '        raise ValueError("yas negatif olamaz")\n'
            '    if kullanici.eposta and "@" not in kullanici.eposta:\n'
            '        raise ValueError("gecersiz eposta")\n'
            "    return True\n"
        )
    },
    # --- hata.yaml ------------------------------------------------------------ #
    "sessiz-yanlis-sonucu-duzelt": {
        "ortalama.py": ("def ortalama(sayilar):\n    return sum(sayilar) / len(sayilar)\n")
    },
    "kenar-durumunda-cokme": {
        "bol.py": (
            "def ortalama_bol(sayilar, bolen):\n"
            "    if not sayilar:\n        return 0.0\n"
            "    return sum(sayilar) / len(sayilar) / bolen\n"
        )
    },
    "yanlis-anahtar-traceback": {
        "rapor.py": (
            "from veri import KAYITLAR\n\n\n"
            "def ozet():\n"
            "    return \", \".join(f\"{kayit['ad']}:{kayit['puan']}\" for kayit in KAYITLAR)\n\n\n"
            'if __name__ == "__main__":\n    print(ozet())\n'
        )
    },
    "iki-testten-birini-bozmadan-duzelt": {
        "metin.py": "def baslik(metin):\n    return metin.strip().upper()\n"
    },
    "yanlis-sinir-degeri": {
        "indirim.py": (
            "def indirim_orani(tutar):\n    if tutar >= 100:\n        return 0.10\n    return 0.0\n"
        )
    },
    "mevcut-projeye-uy": {
        "matematik.py": (
            '"""Matematik yardimcilari."""\n\n\n'
            "def topla(a: int, b: int) -> int:\n"
            '    """Iki sayiyi toplar."""\n    return a + b\n\n\n'
            "def cikar(a: int, b: int) -> int:\n"
            '    """Iki sayinin farkini dondurur."""\n    return a - b\n'
        )
    },
    # --- bakim.yaml: günlük bakım işleri ---
    "eski-adi-koruyarak-yeniden-adlandir": {
        "metin.py": (
            "def ozetle(s, sinir=5):\n"
            '    return s if len(s) <= sinir else s[:sinir] + "..."\n\n\n'
            "#: Eski ad korunur: çağıran kod kırılmamalı.\n"
            "kisalt = ozetle\n"
        )
    },
    "sessiz-hata-yutmayi-bitir": {
        "ayar.py": (
            "import json\n\n\n"
            "def oku(yol):\n"
            "    try:\n"
            '        with open(yol, encoding="utf-8") as f:\n'
            "            return json.load(f)\n"
            "    except FileNotFoundError:\n"
            "        return None\n"
            "    except json.JSONDecodeError as hata:\n"
            '        raise ValueError(f"bozuk yapılandırma: {yol}") from hata\n'
        )
    },
    "dongusel-importu-coz": {
        "siparis.py": (
            "def siparis_ozeti(tutarlar):\n"
            '    return f"{len(tutarlar)} sipariş / {sum(tutarlar)} TL"\n'
        ),
        "kullanici.py": (
            "from siparis import siparis_ozeti\n\n\n"
            "def kullanici_ozeti(ad, tutarlar):\n"
            '    return f"{ad}: {siparis_ozeti(tutarlar)}"\n'
        ),
    },
    "surum-sabitini-tek-kaynaga-indir": {
        "paket/__init__.py": 'SURUM = "2.0.0"\n',
        "paket/cli.py": ('from . import SURUM\n\n\ndef surum_yaz():\n    return f"v{SURUM}"\n'),
        "paket/rapor.py": (
            'from . import SURUM\n\n\ndef baslik():\n    return f"Rapor (v{SURUM})"\n'
        ),
    },
    "sinir-durumu-bos-girdi": {
        "ortalama.py": (
            "def ortalama(sayilar):\n"
            "    if not sayilar:\n"
            "        return 0.0\n"
            "    return sum(sayilar) / len(sayilar)\n"
        )
    },
    "tekrari-ortak-yardimciya-cikar": {
        "fiyat.py": (
            "def _yuvarla(tutar):\n"
            "    return int(tutar * 100 + 0.5) / 100\n\n\n"
            "def net(tutar):\n"
            "    return _yuvarla(tutar)\n\n\n"
            "def brut(tutar):\n"
            "    return _yuvarla(tutar * 1.2)\n\n\n"
            "def indirimli(tutar, oran):\n"
            "    return _yuvarla(tutar * (1 - oran))\n"
        )
    },
    "turkce-karakterli-slug": {
        "slug.py": (
            "import re\n\n"
            '_TR = str.maketrans("çğıöşüÇĞIİÖŞÜ", "cgiosuCGIIOSU")\n\n\n'
            "def slug(metin):\n"
            "    duz = metin.translate(_TR).lower()\n"
            '    return re.sub(r"[^a-z0-9]+", "-", duz).strip("-")\n'
        )
    },
    "varsayilanlari-birlestir": {
        "yapilandirma.py": (
            'VARSAYILAN = {"port": 8080, "log": {"seviye": "info", "dosya": "app.log"}}\n\n\n'
            "def _birlestir(taban, ustune):\n"
            "    sonuc = dict(taban)\n"
            "    for anahtar, deger in (ustune or {}).items():\n"
            "        mevcut = sonuc.get(anahtar)\n"
            "        if isinstance(mevcut, dict) and isinstance(deger, dict):\n"
            "            sonuc[anahtar] = _birlestir(mevcut, deger)\n"
            "        else:\n"
            "            sonuc[anahtar] = deger\n"
            "    return sonuc\n\n\n"
            "def yukle(kullanici):\n"
            "    return _birlestir(VARSAYILAN, kullanici)\n"
        )
    },
}


#: Referans çözümü DOSYA olarak yazılamayan görevler.
#
# `arena` ölçütü gerçek Chromium ile davranış sınar (`python -m evals.behavioral`);
# doğru çözümü `evals/fixtures/arena_reference/index.html` fikstürüdür ve tarayıcı
# gerektirdiği için bu ağsız kapıda çalıştırılamaz. Ölçütün kendisi
# `tests/test_behavioral_eval.py` içinde ayrıca sınanır.
TARAYICI_GEREKTIREN = frozenset({"arena-survival-core-loop"})


def _exit_code_gorevleri():
    gorevler = []
    for suite in SUITES:
        gorevler.extend(
            gorev
            for gorev in load_tasks(suite)
            if gorev.criterion.kind is CriterionKind.EXIT_CODE
            and gorev.id not in TARAYICI_GEREKTIREN
        )
    return gorevler


def _gorev_kimlikleri():
    return [gorev.id for gorev in _exit_code_gorevleri()]


@pytest.mark.parametrize("gorev_id", _gorev_kimlikleri())
def test_olcut_dogru_cozumu_kabul_eder(gorev_id, tmp_path: Path):
    """Referans çözüm ölçütü GEÇMELİ; geçmiyorsa ölçüt fazla dar ya da hatalı."""
    gorev = next(g for g in _exit_code_gorevleri() if g.id == gorev_id)
    cozum = REFERANS_COZUMLER.get(gorev_id)
    if cozum is None:
        pytest.fail(
            f"'{gorev_id}' için referans çözüm yok. Yeni eval görevi eklendiğinde "
            "REFERANS_COZUMLER'e de eklenmeli — ölçütün doğru çözümü kabul ettiği "
            "doğrulanmadan sete girmemeli."
        )

    for yol, icerik in {**gorev.setup, **cozum}.items():
        hedef = tmp_path / yol
        hedef.parent.mkdir(parents=True, exist_ok=True)
        if icerik.startswith("base64:"):
            hedef.write_bytes(base64.b64decode(icerik.removeprefix("base64:")))
        else:
            hedef.write_text(icerik, encoding="utf-8")

    komut = (gorev.criterion.command or "").replace("python ", f"{sys.executable} ")
    sonuc = subprocess.run(
        komut,
        shell=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert sonuc.returncode == gorev.criterion.expected_exit_code, (
        f"'{gorev_id}' ölçütü DOĞRU çözümü reddetti.\n"
        f"komut: {komut}\nstdout: {sonuc.stdout}\nstderr: {sonuc.stderr}"
    )


def test_her_exit_code_gorevinin_referans_cozumu_var():
    """Set büyüdüğünde bu test unutulan referans çözümü hemen gösterir."""
    eksik = [gorev.id for gorev in _exit_code_gorevleri() if gorev.id not in REFERANS_COZUMLER]
    assert not eksik, f"referans çözümü olmayan eval görevleri: {eksik}"
