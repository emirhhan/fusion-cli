"""Dosya araçları — okuma, yazma, benzersiz eşleşme ve atomik çoklu düzenleme."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry, files
from fusion_cli.tools.args import ArgumentError
from fusion_cli.tools.files import parse_edits


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


@pytest.fixture
def registry():
    return build_registry()


async def _calistir(registry, context, ad, **args):
    return await registry.execute(ad, args, context)


async def test_yazma_ve_okuma_dongusu(registry, context, tmp_path):
    yazma = await _calistir(registry, context, "write_file", path="a.txt", content="merhaba\ndunya")

    assert yazma.ok and "oluşturuldu" in yazma.output
    okuma = await _calistir(registry, context, "read_file", path="a.txt")
    assert okuma.ok
    assert "1\tmerhaba" in okuma.output and "2\tdunya" in okuma.output


async def test_var_olan_dosyaya_yazmak_guncelleme_der(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("eski", encoding="utf-8")
    # Tam okuma, üzerine yazmanın ÖN KOŞULUDUR: aşağıdaki teste bak.
    await _calistir(registry, context, "read_file", path="a.txt")

    sonuc = await _calistir(registry, context, "write_file", path="a.txt", content="yeni")

    assert "güncellendi" in sonuc.output


async def test_yazma_ust_dizinleri_olusturur(registry, context, tmp_path):
    await _calistir(registry, context, "write_file", path="derin/yol/a.txt", content="x")

    assert (tmp_path / "derin" / "yol" / "a.txt").read_text(encoding="utf-8") == "x"


async def test_olmayan_dosya_okumasi_basarisiz_doner(registry, context):
    sonuc = await _calistir(registry, context, "read_file", path="yok.txt")

    assert not sonuc.ok and "Dosya yok" in sonuc.output


async def test_dizin_okumaya_calisirsa_anlasilir_hata(registry, context, tmp_path):
    (tmp_path / "klasor").mkdir()

    sonuc = await _calistir(registry, context, "read_file", path="klasor")

    assert not sonuc.ok and "dizin" in sonuc.output


async def test_ikili_dosya_okunamaz(registry, context, tmp_path):
    (tmp_path / "resim.png").write_bytes(b"\x89PNG\x00\xff\xfe")

    sonuc = await _calistir(registry, context, "read_file", path="resim.png")

    assert not sonuc.ok and "Metin dosyası değil" in sonuc.output


async def test_bos_dosya_ozel_mesaj_verir(registry, context, tmp_path):
    (tmp_path / "bos.txt").write_text("", encoding="utf-8")

    assert (await _calistir(registry, context, "read_file", path="bos.txt")).output == "(boş dosya)"


async def test_duzenleme_benzersiz_eslesme_ister(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("tekrar\ntekrar\n", encoding="utf-8")

    sonuc = await _calistir(registry, context, "edit_file", path="a.txt", old="tekrar", new="yeni")

    assert not sonuc.ok and "2 kez geçiyor" in sonuc.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "tekrar\ntekrar\n"


async def test_duzenleme_eslesmezse_dosyaya_dokunmaz(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("icerik", encoding="utf-8")

    sonuc = await _calistir(registry, context, "edit_file", path="a.txt", old="yok", new="yeni")

    assert not sonuc.ok and "bulunamadı" in sonuc.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "icerik"


async def test_basarili_duzenleme_uygulanir(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("merhaba dunya", encoding="utf-8")

    sonuc = await _calistir(registry, context, "edit_file", path="a.txt", old="dunya", new="evren")

    assert sonuc.ok
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "merhaba evren"


async def test_multi_edit_atomiktir_biri_tutmazsa_hicbiri_uygulanmaz(registry, context, tmp_path):
    dosya = tmp_path / "a.txt"
    dosya.write_text("bir\niki\n", encoding="utf-8")

    sonuc = await _calistir(
        registry,
        context,
        "multi_edit",
        path="a.txt",
        edits=[{"old": "bir", "new": "1"}, {"old": "olmayan", "new": "x"}],
    )

    assert not sonuc.ok
    assert dosya.read_text(encoding="utf-8") == "bir\niki\n"


async def test_multi_edit_hepsi_tutunca_uygulanir(registry, context, tmp_path):
    dosya = tmp_path / "a.txt"
    dosya.write_text("bir\niki\n", encoding="utf-8")

    sonuc = await _calistir(
        registry,
        context,
        "multi_edit",
        path="a.txt",
        edits=[{"old": "bir", "new": "1"}, {"old": "iki", "new": "2"}],
    )

    assert sonuc.ok
    assert dosya.read_text(encoding="utf-8") == "1\n2\n"


async def test_list_dir_gizli_dosyalari_gizler_ama_beyaz_listeyi_gosterir(
    registry, context, tmp_path
):
    (tmp_path / "gorunur.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".gizli").write_text("x", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("x", encoding="utf-8")

    cikti = (await _calistir(registry, context, "list_dir", path=".")).output

    assert "gorunur.txt" in cikti
    assert ".gizli" not in cikti
    assert ".gitignore" in cikti


async def test_bos_dizin_ozel_mesaj(registry, context, tmp_path):
    (tmp_path / "bos").mkdir()

    assert (await _calistir(registry, context, "list_dir", path="bos")).output == "(boş dizin)"


async def test_eksik_argüman_anlasilir_hataya_donusur(registry, context):
    sonuc = await registry.execute("read_file", {}, context)

    assert not sonuc.ok and "path" in sonuc.output


async def test_bozuk_edits_bicimi_reddedilir():
    with pytest.raises(ArgumentError, match="'old' boş olmayan"):
        parse_edits([{"new": "x"}])


async def test_mutlak_yol_kok_dizine_baglanmaz(registry, context, tmp_path):
    hedef = tmp_path / "disarida.txt"

    await _calistir(registry, context, "write_file", path=str(hedef), content="x")

    assert hedef.read_text(encoding="utf-8") == "x"


# --- Kısıtlı kip: kök dışına erişim reddi ---------------------------------- #


@pytest.fixture
def kisitli_context(tmp_path):
    calisma = tmp_path / "proje"
    calisma.mkdir()
    return ToolContext(root=calisma, restrict_to_root=True)


async def test_kisitli_kipte_kok_ici_yazma_calisir(registry, kisitli_context):
    sonuc = await _calistir(registry, kisitli_context, "write_file", path="a.txt", content="x")

    assert sonuc.ok
    assert (kisitli_context.root / "a.txt").read_text(encoding="utf-8") == "x"


async def test_kisitli_kipte_mutlak_kok_disi_yazma_reddedilir(registry, kisitli_context, tmp_path):
    disarida = tmp_path / "disarida.txt"

    sonuc = await _calistir(
        registry, kisitli_context, "write_file", path=str(disarida), content="x"
    )

    assert not sonuc.ok and "kök" in sonuc.output
    assert not disarida.exists()


async def test_kisitli_kipte_traversal_kok_disina_cikamaz(registry, kisitli_context, tmp_path):
    (tmp_path / "gizli.txt").write_text("sir", encoding="utf-8")

    sonuc = await _calistir(registry, kisitli_context, "read_file", path="../gizli.txt")

    assert not sonuc.ok and "kök" in sonuc.output


async def test_kisitli_kipte_symlink_kok_disini_hedeflerse_reddedilir(
    registry, kisitli_context, tmp_path
):
    (tmp_path / "gizli.txt").write_text("sir", encoding="utf-8")
    (kisitli_context.root / "link.txt").symlink_to(tmp_path / "gizli.txt")

    sonuc = await _calistir(registry, kisitli_context, "read_file", path="link.txt")

    assert not sonuc.ok and "kök" in sonuc.output


async def test_kisitsiz_kipte_kok_disina_yazilabilir(registry, tmp_path):
    """restrict_to_root=False (yeni varsayılan): kök dışındaki projelerde de çalışılabilir."""
    calisma = tmp_path / "proje"
    calisma.mkdir()
    context = ToolContext(root=calisma, restrict_to_root=False)
    disarida = tmp_path / "disarida.txt"

    sonuc = await _calistir(registry, context, "write_file", path=str(disarida), content="x")

    assert sonuc.ok
    assert disarida.read_text(encoding="utf-8") == "x"


def test_dizin_kisiti_varsayilan_kapali():
    """Ürün varsayılanı: dosya araçları kök dışına çıkabilir (kullanıcı seçimi)."""
    from fusion_cli.config.loader import load_config

    config = load_config(None)
    assert config.runtime.restrict_to_root is False


# --- Yazılan dosyaların izi -------------------------------------------------- #
#
# Doğrulama kapısı YALNIZCA agent'ın dokunduğu dosyalara bakmalı; kök dizini
# taramak, agent'ın hiç görmediği dosyalar hakkında bulgu üretirdi.


def test_yazilan_dosya_iz_birakir(tmp_path):
    context = ToolContext(root=tmp_path)

    files.write_file({"path": "a.html", "content": "<h1>x</h1>"}, context)

    assert tmp_path / "a.html" in context.touched


def test_duzenlenen_dosya_iz_birakir(tmp_path):
    (tmp_path / "a.css").write_text("eski", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    files.edit_file({"path": "a.css", "old": "eski", "new": "yeni"}, context)

    assert tmp_path / "a.css" in context.touched


def test_okunan_dosya_iz_birakmaz(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    files.read_file({"path": "a.txt"}, context)

    assert not context.touched


def test_basarisiz_duzenleme_iz_birakmaz(tmp_path):
    (tmp_path / "a.txt").write_text("icerik", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    files.edit_file({"path": "a.txt", "old": "olmayan", "new": "y"}, context)

    assert not context.touched


# --- Toplu değiştirme -------------------------------------------------------- #
#
# Gerçek hata: kapı "19 boş bağlantı var" dedi, model 19 özdeş href="#" metnini
# değiştirmek istedi ve araç "benzersiz olmalı" diye reddetti. Tek tek düzeltmek 19
# çağrı, tamamını yeniden yazmak <script> etiketini düşürme riski. Model doğru şeyi
# istedi, araç veremedi; tur 62 model çağrısı harcayıp düzeltemedi.


def test_replace_all_tum_eslesmeleri_degistirir(tmp_path):
    dosya = tmp_path / "a.html"
    dosya.write_text('<a href="#">1</a><a href="#">2</a><a href="#">3</a>', encoding="utf-8")
    context = ToolContext(root=tmp_path)

    sonuc = files.edit_file(
        {"path": "a.html", "old": 'href="#"', "new": 'href="/kurumsal"', "replace_all": True},
        context,
    )

    assert sonuc.ok, sonuc.output
    assert 'href="#"' not in dosya.read_text(encoding="utf-8")
    assert "3" in sonuc.output, "kaç değişiklik yapıldığı bildirilmeli"


def test_replace_all_olmadan_benzersizlik_hala_sart(tmp_path):
    """Varsayılan davranış korunur: kör toplu değiştirme kazara veri bozar."""
    dosya = tmp_path / "a.html"
    dosya.write_text('<a href="#">1</a><a href="#">2</a>', encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.html", "old": 'href="#"', "new": "x"}, ToolContext(root=tmp_path)
    )

    assert not sonuc.ok
    assert "benzersiz" in sonuc.output


def test_replace_all_eslesme_yoksa_yine_hata_verir(tmp_path):
    (tmp_path / "a.txt").write_text("icerik", encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.txt", "old": "yok", "new": "x", "replace_all": True},
        ToolContext(root=tmp_path),
    )

    assert not sonuc.ok
    assert "bulunamadı" in sonuc.output


def test_benzersizlik_hatasi_replace_all_secenegini_soyler(tmp_path):
    """Model çıkış yolunu bilmeli; aksi halde döngüye giriyor."""
    dosya = tmp_path / "a.html"
    dosya.write_text('<a href="#">1</a><a href="#">2</a>', encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.html", "old": 'href="#"', "new": "x"}, ToolContext(root=tmp_path)
    )

    assert "replace_all" in sonuc.output


def test_multi_edit_de_replace_all_destekler(tmp_path):
    """Aynı sıkışma multi_edit'te de vardı: her düzenleme benzersizlik istiyordu."""
    dosya = tmp_path / "a.html"
    dosya.write_text('<a href="#">1</a><a href="#">2</a><p>eski</p>', encoding="utf-8")

    sonuc = files.multi_edit(
        {
            "path": "a.html",
            "edits": [
                {"old": 'href="#"', "new": 'href="/x"', "replace_all": True},
                {"old": "eski", "new": "yeni"},
            ],
        },
        ToolContext(root=tmp_path),
    )

    metin = dosya.read_text(encoding="utf-8")
    assert sonuc.ok, sonuc.output
    assert 'href="#"' not in metin
    assert "yeni" in metin


# --- Eşleşmeyen 'old' teşhisi ------------------------------------------------ #
#
# Dört koşudaki EN SIK araç hatası buydu (3 kez). Sebebi büyük ihtimalle şu tuzak:
# read_file "    1\tiçerik" biçiminde satır numarası ekliyor, model bunu ayıklamayı
# unutunca eşleşme tutmuyor ve "bulunamadı" mesajı NEDENİNİ söylemiyordu.


def test_satir_numarasi_iceren_old_tolere_edilir(tmp_path):
    """read_file çıktısından kopyalanan 'old' reddedilmez, temizlenip uygulanır.

    Eskiden teşhis ediliyor ama reddediliyordu: model doğru yeri hedeflemiş olsa
    bile tur yanıyor ve "yazmak başarısız" gradyanı büyüyordu.
    """
    dosya = tmp_path / "a.py"
    dosya.write_text("def f():\n    return 1\n", encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.py", "old": "    1\tdef f():", "new": "def g():"},
        ToolContext(root=tmp_path),
    )

    assert sonuc.ok, sonuc.output
    assert dosya.read_text(encoding="utf-8") == "def g():\n    return 1\n"


def test_soyulunca_da_eslesmeyen_old_teshis_edilir(tmp_path):
    """Tolerans yalnızca sonuç GERÇEKTEN eşleşiyorsa; yoksa teşhis sürüyor."""
    dosya = tmp_path / "a.py"
    dosya.write_text("def f():\n", encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.py", "old": "   9\tdef yok():", "new": "x"},
        ToolContext(root=tmp_path),
    )

    assert not sonuc.ok
    assert "satır numarası" in sonuc.output.lower()


def test_girinti_farki_teshis_edilir(tmp_path):
    dosya = tmp_path / "a.py"
    # Dosyada SEKME, modelin gönderdiğinde BOŞLUK var: alt-dize olarak da eşleşmez.
    dosya.write_text("def f():\n\treturn 1\n", encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.py", "old": "    return 1", "new": "    return 2"},
        ToolContext(root=tmp_path),
    )

    assert not sonuc.ok
    assert "girinti" in sonuc.output.lower() or "boşluk" in sonuc.output.lower()


def test_gercekten_olmayan_metin_icin_sade_mesaj(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n", encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.py", "old": "class Foo", "new": "class Bar"}, ToolContext(root=tmp_path)
    )

    assert not sonuc.ok
    assert "bulunamadı" in sonuc.output
    assert "satır numarası" not in sonuc.output.lower()


def test_buyuk_dosya_kirpildigini_soyler(tmp_path):
    """Sessiz kırpma modele dosyanın tamamını okudum yanılgısı verir."""
    from fusion_cli.core.constants import MAX_READ_BYTES

    dosya = tmp_path / "buyuk.txt"
    dosya.write_text("x" * (MAX_READ_BYTES + 5_000), encoding="utf-8")

    sonuc = files.read_file({"path": "buyuk.txt"}, ToolContext(root=tmp_path))

    # Türkçe büyük/küçük dönüşümü tuzaklıdır ("KIRPILDI".lower() → "kirpildi");
    # metin olduğu gibi aranır.
    assert "KIRPILDI" in sonuc.output


# --- Eksik path kurtarması --------------------------------------------------- #
#
# Beş koşuda toplam 14 kez oldu; yarım kalan 5. koşuda write_file çağrılarının
# %50'sini vurdu. Model içeriği önce yazıp sondaki küçük 'path' alanını düşürüyor.
# Her hata, 15 KB'lık içeriğin baştan üretilmesi demekti.


def test_path_eksikse_icerik_saklanir(tmp_path):
    context = ToolContext(root=tmp_path)

    sonuc = files.write_file({"content": "<h1>uzun içerik</h1>"}, context)

    assert not sonuc.ok
    assert context.pending.content == "<h1>uzun içerik</h1>"
    # Türkçe küçültme tuzaklıdır ("YALNIZCA".lower() → "yalnizca"); metin olduğu gibi aranır.
    assert "YALNIZCA" in sonuc.output, "modele içeriği tekrar göndermemesi söylenmeli"


def test_saklanan_icerik_yalnizca_path_ile_yazilir(tmp_path):
    context = ToolContext(root=tmp_path)
    files.write_file({"content": "<h1>merhaba</h1>"}, context)

    sonuc = files.write_file({"path": "a.html"}, context)

    assert sonuc.ok, sonuc.output
    assert (tmp_path / "a.html").read_text(encoding="utf-8") == "<h1>merhaba</h1>"


def test_kurtarma_kullanildiktan_sonra_temizlenir(tmp_path):
    """Saklanan içerik bir kez kullanılır; sonraki çağrıya sızmamalı."""
    context = ToolContext(root=tmp_path)
    files.write_file({"content": "ilk"}, context)
    files.write_file({"path": "a.txt"}, context)

    sonuc = files.write_file({"path": "b.txt"}, context)

    assert not sonuc.ok
    assert context.pending.content == ""


def test_content_verilirse_saklanan_yok_sayilir(tmp_path):
    """Model içeriği gerçekten gönderdiyse eski saklanan içerik ASLA kullanılmaz."""
    context = ToolContext(root=tmp_path)
    files.write_file({"content": "eski"}, context)

    files.write_file({"path": "a.txt", "content": "yeni"}, context)

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "yeni"


def test_ikisi_de_yoksa_arguman_hatasi(tmp_path):
    """path da content da yoksa aracın kendi doğrulaması devreye girer."""
    with pytest.raises(ArgumentError):
        files.write_file({}, ToolContext(root=tmp_path))


# --- Ek izinli dizinler (--add-dir) ----------------------------------------- #


async def test_varsayilan_kisitlidir(registry, tmp_path):
    """Tüm disk varsayılan erişim alanı DEĞİLDİR.

    Kısıtlama opt-in bırakıldığı sürece kimse açmıyordu; agent her kurulumda
    kullanıcının tüm dosya sistemine yazabiliyordu.
    """
    calisma = tmp_path / "proje"
    calisma.mkdir()
    disarida = tmp_path / "disarida.txt"

    sonuc = await _calistir(
        registry, ToolContext(root=calisma), "write_file", path=str(disarida), content="x"
    )

    assert not sonuc.ok
    assert not disarida.exists()


async def test_ek_dizin_acikca_izin_verilince_erisilir(registry, tmp_path):
    calisma = tmp_path / "proje"
    calisma.mkdir()
    paylasilan = tmp_path / "paylasilan"
    paylasilan.mkdir()
    context = ToolContext(root=calisma, extra_roots=(paylasilan,))

    sonuc = await _calistir(
        registry, context, "write_file", path=str(paylasilan / "a.txt"), content="x"
    )

    assert sonuc.ok
    assert (paylasilan / "a.txt").read_text(encoding="utf-8") == "x"


async def test_ek_dizin_yalnizca_kendi_altini_acar(registry, tmp_path):
    """`--add-dir` bir kapı değil, dar bir pencere olmalı."""
    calisma = tmp_path / "proje"
    calisma.mkdir()
    paylasilan = tmp_path / "paylasilan"
    paylasilan.mkdir()
    baska = tmp_path / "baska.txt"
    context = ToolContext(root=calisma, extra_roots=(paylasilan,))

    sonuc = await _calistir(registry, context, "write_file", path=str(baska), content="x")

    assert not sonuc.ok
    assert not baska.exists()


async def test_ek_dizin_symlink_ile_asilamaz(registry, tmp_path):
    calisma = tmp_path / "proje"
    calisma.mkdir()
    paylasilan = tmp_path / "paylasilan"
    paylasilan.mkdir()
    (tmp_path / "gizli.txt").write_text("sir", encoding="utf-8")
    (paylasilan / "kacis").symlink_to(tmp_path / "gizli.txt")
    context = ToolContext(root=calisma, extra_roots=(paylasilan,))

    sonuc = await _calistir(registry, context, "read_file", path=str(paylasilan / "kacis"))

    assert not sonuc.ok


# --- Atomik yazma ----------------------------------------------------------- #


async def test_yazma_yarim_kalirsa_eski_icerik_korunur(registry, tmp_path, monkeypatch):
    """Yazma ortasında kesilme dosyayı yarım bırakmamalı.

    `write_text` doğrudan hedefe yazar: süreç o anda ölürse dosya yarım kalır ve
    kullanıcının çalışan kodu yerine bozuk bir dosya durur. Geçici dosyaya yazıp
    yerine taşımak bu pencereyi tamamen kapatır.
    """
    hedef = tmp_path / "onemli.py"
    hedef.write_text("eski = 'calisiyor'\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    def _patlat(self, hedef):
        raise OSError("disk doldu")

    monkeypatch.setattr(Path, "replace", _patlat)

    sonuc = await _calistir(registry, context, "write_file", path="onemli.py", content="yeni\n")

    assert not sonuc.ok
    assert hedef.read_text(encoding="utf-8") == "eski = 'calisiyor'\n", "eski içerik korunmalı"


async def test_yazma_gecici_dosya_birakmaz(registry, tmp_path):
    context = ToolContext(root=tmp_path)

    await _calistir(registry, context, "write_file", path="a.txt", content="x")

    artiklar = [p.name for p in tmp_path.iterdir() if p.name != "a.txt"]
    assert artiklar == [], f"geçici dosya kaldı: {artiklar}"


# --- Okunmamış dosyanın üzerine yazma koruması ------------------------------- #
#
# `write_file` dosyanın TAMAMINI değiştirir. Model dosyayı hiç okumadıysa ya da
# kırpılmış okuduysa gönderdiği "tam içerik" gerçekten tam değildir ve kesme
# noktasından sonrası sessizce yok olur. `read_file` açıklaması zaten "değiştirmeden
# ÖNCE mutlaka oku" diyor; burada o kural uygulanır.


async def test_okunmamis_var_olan_dosyanin_uzerine_yazilmaz(registry, context, tmp_path):
    hedef = tmp_path / "a.txt"
    hedef.write_text("değerli içerik", encoding="utf-8")

    sonuc = await _calistir(registry, context, "write_file", path="a.txt", content="yeni")

    assert not sonuc.ok
    assert "edit_file" in sonuc.output
    # En önemlisi: dosya DEĞİŞMEMİŞ olmalı.
    assert hedef.read_text(encoding="utf-8") == "değerli içerik"


async def test_yeni_dosya_olusturmak_okuma_gerektirmez(registry, context, tmp_path):
    """Koruma yalnızca VAR OLAN dosyaya karşıdır; yeni dosya serbestçe yazılır."""
    sonuc = await _calistir(registry, context, "write_file", path="yeni.txt", content="x")

    assert sonuc.ok
    assert (tmp_path / "yeni.txt").read_text(encoding="utf-8") == "x"


async def test_kirpilmis_okuma_tam_okuma_sayilmaz(registry, context, tmp_path, monkeypatch):
    """Asıl veri kaybı yolu: büyük dosya kırpılarak okunur, sonra üzerine yazılır."""
    from fusion_cli.tools import files

    monkeypatch.setattr(files, "MAX_READ_BYTES", 10)
    hedef = tmp_path / "buyuk.txt"
    tam = "satir\n" * 50
    hedef.write_text(tam, encoding="utf-8")

    okuma = await _calistir(registry, context, "read_file", path="buyuk.txt")
    assert "KIRPILDI" in okuma.output

    sonuc = await _calistir(
        registry, context, "write_file", path="buyuk.txt", content="gördüğüm kadarı"
    )

    assert not sonuc.ok
    assert hedef.read_text(encoding="utf-8") == tam, "kırpılan kısım korunmalı"


async def test_edit_file_okuma_sarti_aramaz(registry, context, tmp_path):
    """edit_file yalnızca eşleşen parçayı değiştirir; görmediğini silemez."""
    hedef = tmp_path / "a.py"
    hedef.write_text("a = 1\nb = 2\n", encoding="utf-8")

    sonuc = await _calistir(registry, context, "edit_file", path="a.py", old="b = 2", new="b = 3")

    assert sonuc.ok
    assert hedef.read_text(encoding="utf-8") == "a = 1\nb = 3\n"


# --------------------------------------------------------------------------- #
# "Önce oku" kapısı — koruma ile ölü kilit arasındaki sınır
# --------------------------------------------------------------------------- #


def test_okunmamis_var_olan_dosya_toptan_yazilamaz(context):
    hedef = context.root / "app.py"
    hedef.write_text("kullanıcının kodu\nikinci satır\n", encoding="utf-8")

    sonuc = files.write_file({"path": "app.py", "content": "yeni"}, context)

    assert not sonuc.ok
    assert "tam içeriğini okumadın" in sonuc.output
    assert hedef.read_text(encoding="utf-8").startswith("kullanıcının kodu")


def test_tam_okunmus_dosya_toptan_yazilabilir(context):
    hedef = context.root / "app.py"
    hedef.write_text("eski", encoding="utf-8")
    files.read_file({"path": "app.py"}, context)

    sonuc = files.write_file({"path": "app.py", "content": "yeni"}, context)

    assert sonuc.ok
    assert hedef.read_text(encoding="utf-8") == "yeni"


def test_agentin_bu_turda_yarattigi_dosya_okumadan_doldurulabilir(context):
    """Ölü kilit: iskele dosyasını doldurmak için önce onu okumak zorunda kalınıyordu."""
    hedef = context.root / "index.html"
    files.write_file({"path": "index.html", "content": "<!-- iskele -->"}, context)

    sonuc = files.write_file({"path": "index.html", "content": "<h1>gerçek</h1>"}, context)

    assert sonuc.ok, sonuc.output
    assert hedef.read_text(encoding="utf-8") == "<h1>gerçek</h1>"


def test_onceki_turdan_kalan_dosya_yine_okuma_ister(context):
    """Muafiyet yalnızca BU tur için: değişiklik kümesi boşsa koruma tam güçtedir."""
    hedef = context.root / "index.html"
    hedef.write_text("<h1>önceki tur</h1>", encoding="utf-8")

    sonuc = files.write_file({"path": "index.html", "content": "yeni"}, context)

    assert not sonuc.ok
    assert hedef.read_text(encoding="utf-8") == "<h1>önceki tur</h1>"
