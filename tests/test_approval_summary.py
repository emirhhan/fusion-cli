import pytest

from fusion_cli.appserver.approval_summary import approval_summary


@pytest.mark.parametrize(
    ("arac", "argumanlar", "baslik", "hedef"),
    [
        ("run_shell", {"command": "npm test"}, "Bu komut çalıştırılsın mı?", "npm test"),
        ("bash", {"command": "git push"}, "Bu komut çalıştırılsın mı?", "git push"),
        ("write_file", {"path": "src/a.ts", "content": "x"}, "Bu dosya yazılsın mı?", "src/a.ts"),
        ("edit_file", {"path": "b.py"}, "Bu dosya düzenlensin mi?", "b.py"),
        (
            "chrome_navigate",
            {"url": "https://ads.google.com"},
            "Tarayıcıda bu işlem yapılsın mı?",
            "https://ads.google.com",
        ),
        ("desktop_type", {"text": "merhaba"}, "Bilgisayarında bu işlem yapılsın mı?", "merhaba"),
        (
            "novamira__update_product",
            {"id": 5},
            "novamira üzerinde “update_product” çalıştırılsın mı?",
            "",
        ),
        ("gizemli", {}, "“gizemli” aracı çalıştırılsın mı?", ""),
    ],
)
def test_izin_karti_insan_dilinde_baslik_ve_hedef_verir(arac, argumanlar, baslik, hedef):
    assert approval_summary(arac, argumanlar) == (baslik, hedef)


def test_yetenek_gecidinde_calisacak_yetenek_ve_parametreler_gosterilir():
    baslik, hedef = approval_summary(
        "motogate__mcp-adapter-execute-ability",
        {"ability_name": "woocommerce/product-update", "parameters": {"id": 5, "fiyat": 100}},
    )
    assert baslik == "motogate üzerinde “woocommerce/product-update” çalıştırılsın mı?"
    assert '"fiyat": 100' in hedef
