"""Geliştirici araçları algılaması: kurulu olanı bulur, eksiğe indirme bağlantısı verir."""

from __future__ import annotations

from fusion_cli.appserver.dev_tools import detect_dev_tools


def test_kurulu_arac_surumuyle_eksik_arac_indirme_baglantisiyla_doner() -> None:
    kurulu = {"node": "/x/node", "git": "/x/git"}

    sonuc = detect_dev_tools(
        find_command=kurulu.get, read_version=lambda yol, bayrak: f"{yol} {bayrak}"
    )

    satirlar = {satir["id"]: satir for satir in sonuc["araclar"]}  # type: ignore[union-attr]
    assert sonuc["ok"] is True
    assert satirlar["node"]["kurulu"] is True
    assert satirlar["node"]["surum"] == "/x/node --version"
    assert satirlar["python"]["kurulu"] is False
    assert satirlar["python"]["surum"] is None
    assert str(satirlar["python"]["indirme"]).startswith("https://www.python.org")


def test_python_icin_ikinci_komut_adi_denenir() -> None:
    sonuc = detect_dev_tools(
        find_command={"python": "/x/python"}.get, read_version=lambda yol, bayrak: "Python 3"
    )

    python = next(s for s in sonuc["araclar"] if s["id"] == "python")  # type: ignore[union-attr]
    assert python["kurulu"] is True


def test_surum_okunamazsa_arac_yine_kurulu_sayilir() -> None:
    sonuc = detect_dev_tools(find_command=lambda ad: f"/x/{ad}", read_version=lambda y, b: None)

    assert all(s["kurulu"] and s["surum"] is None for s in sonuc["araclar"])  # type: ignore[union-attr]
