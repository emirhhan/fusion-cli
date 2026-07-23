"""Dosya araçları — okuma, yazma, benzersiz eşleşme ve atomik çoklu düzenleme."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools.args import ArgumentError
from fusion_cli.tools.files import parse_edits


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


@pytest.fixture
def registry():
    return build_registry()


def _calistir(registry, context, ad, **args):
    return registry.execute(ad, args, context)


def test_yazma_ve_okuma_dongusu(registry, context, tmp_path):
    yazma = _calistir(registry, context, "write_file", path="a.txt", content="merhaba\ndunya")

    assert yazma.ok and "oluşturuldu" in yazma.output
    okuma = _calistir(registry, context, "read_file", path="a.txt")
    assert okuma.ok
    assert "1\tmerhaba" in okuma.output and "2\tdunya" in okuma.output


def test_var_olan_dosyaya_yazmak_guncelleme_der(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("eski", encoding="utf-8")

    sonuc = _calistir(registry, context, "write_file", path="a.txt", content="yeni")

    assert "güncellendi" in sonuc.output


def test_yazma_ust_dizinleri_olusturur(registry, context, tmp_path):
    _calistir(registry, context, "write_file", path="derin/yol/a.txt", content="x")

    assert (tmp_path / "derin" / "yol" / "a.txt").read_text(encoding="utf-8") == "x"


def test_olmayan_dosya_okumasi_basarisiz_doner(registry, context):
    sonuc = _calistir(registry, context, "read_file", path="yok.txt")

    assert not sonuc.ok and "Dosya yok" in sonuc.output


def test_dizin_okumaya_calisirsa_anlasilir_hata(registry, context, tmp_path):
    (tmp_path / "klasor").mkdir()

    sonuc = _calistir(registry, context, "read_file", path="klasor")

    assert not sonuc.ok and "dizin" in sonuc.output


def test_ikili_dosya_okunamaz(registry, context, tmp_path):
    (tmp_path / "resim.png").write_bytes(b"\x89PNG\x00\xff\xfe")

    sonuc = _calistir(registry, context, "read_file", path="resim.png")

    assert not sonuc.ok and "Metin dosyası değil" in sonuc.output


def test_bos_dosya_ozel_mesaj_verir(registry, context, tmp_path):
    (tmp_path / "bos.txt").write_text("", encoding="utf-8")

    assert _calistir(registry, context, "read_file", path="bos.txt").output == "(boş dosya)"


def test_duzenleme_benzersiz_eslesme_ister(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("tekrar\ntekrar\n", encoding="utf-8")

    sonuc = _calistir(registry, context, "edit_file", path="a.txt", old="tekrar", new="yeni")

    assert not sonuc.ok and "2 kez geçiyor" in sonuc.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "tekrar\ntekrar\n"


def test_duzenleme_eslesmezse_dosyaya_dokunmaz(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("icerik", encoding="utf-8")

    sonuc = _calistir(registry, context, "edit_file", path="a.txt", old="yok", new="yeni")

    assert not sonuc.ok and "bulunamadı" in sonuc.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "icerik"


def test_basarili_duzenleme_uygulanir(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("merhaba dunya", encoding="utf-8")

    sonuc = _calistir(registry, context, "edit_file", path="a.txt", old="dunya", new="evren")

    assert sonuc.ok
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "merhaba evren"


def test_multi_edit_atomiktir_biri_tutmazsa_hicbiri_uygulanmaz(registry, context, tmp_path):
    dosya = tmp_path / "a.txt"
    dosya.write_text("bir\niki\n", encoding="utf-8")

    sonuc = _calistir(
        registry,
        context,
        "multi_edit",
        path="a.txt",
        edits=[{"old": "bir", "new": "1"}, {"old": "olmayan", "new": "x"}],
    )

    assert not sonuc.ok
    assert dosya.read_text(encoding="utf-8") == "bir\niki\n"


def test_multi_edit_hepsi_tutunca_uygulanir(registry, context, tmp_path):
    dosya = tmp_path / "a.txt"
    dosya.write_text("bir\niki\n", encoding="utf-8")

    sonuc = _calistir(
        registry,
        context,
        "multi_edit",
        path="a.txt",
        edits=[{"old": "bir", "new": "1"}, {"old": "iki", "new": "2"}],
    )

    assert sonuc.ok
    assert dosya.read_text(encoding="utf-8") == "1\n2\n"


def test_list_dir_gizli_dosyalari_gizler_ama_beyaz_listeyi_gosterir(registry, context, tmp_path):
    (tmp_path / "gorunur.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".gizli").write_text("x", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("x", encoding="utf-8")

    cikti = _calistir(registry, context, "list_dir", path=".").output

    assert "gorunur.txt" in cikti
    assert ".gizli" not in cikti
    assert ".gitignore" in cikti


def test_bos_dizin_ozel_mesaj(registry, context, tmp_path):
    (tmp_path / "bos").mkdir()

    assert _calistir(registry, context, "list_dir", path="bos").output == "(boş dizin)"


def test_eksik_argüman_anlasilir_hataya_donusur(registry, context):
    sonuc = registry.execute("read_file", {}, context)

    assert not sonuc.ok and "path" in sonuc.output


def test_bozuk_edits_bicimi_reddedilir():
    with pytest.raises(ArgumentError, match="'old' boş olmayan"):
        parse_edits([{"new": "x"}])


def test_mutlak_yol_kok_dizine_baglanmaz(registry, context, tmp_path):
    hedef = tmp_path / "disarida.txt"

    _calistir(registry, context, "write_file", path=str(hedef), content="x")

    assert hedef.read_text(encoding="utf-8") == "x"
