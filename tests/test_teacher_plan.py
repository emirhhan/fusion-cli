"""Öğretmen planının görev kararı ve yanıt sözleşmesi testleri."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.teacher_plan import (
    TeacherPlanError,
    classify_teacher_task,
    parse_teacher_plan,
    parse_teacher_review,
)


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("Merhaba", "basit"),
        (
            "Bugünün yerel tarihini, kullandığın modeli ve 17 × 23 sonucunu üç kısa "
            "cümleyle yaz. Web araştırması yapma; tarih için sana verilen çalışma "
            "bağlamını esas al.",
            "basit",
        ),
        ("Bu kavramı açıkla; cevabını üç cümleyle sınırla", "basit"),
        ("README dosyasını oku ve özetle", "basit"),
        ("src/app.py dosyasındaki hatayı düzelt", "orta-buyuk"),
        ("src/app.py içindeki add hatasını düzelt; mevcut testi çalıştır", "orta-buyuk"),
        ("Shopify API ile ürün yayımlama akışını kur ve doğrula", "orta-buyuk"),
        # A4-34: tek belge dosyası / açıkça küçük düzenleme öğretmen planı gerektirmez.
        ("README'ye bir satır ekle", "basit"),
        ("README.md dosyasına kurulum başlığı ekle", "basit"),
        ("src/app.py içindeki yazım hatasını düzelt", "basit"),
        # Kaynak kod + belge birlikte, ya da kod parçası yapıştırılmış görev eskisi gibi.
        ("README.md ve src/app.py dosyalarını güncelle", "orta-buyuk"),
        ("x = 1; y = 2 işlemini açıkla", "basit"),
        ("1. modeli ekle\n2. testi yaz\n3. README güncelle", "orta-buyuk"),
        ("config oluştur; servisi ekle; testi yaz", "orta-buyuk"),
    ],
)
def test_gorev_boyutu_etki_ve_kapsamla_belirlenir(task: str, expected: str) -> None:
    assert classify_teacher_task(task).size == expected


def test_yapilandirilmis_ogretmen_plani_ayristirilir() -> None:
    answer = """[öğretmen · sahte]
```json
{
  "adimlar": ["İlgili dosyayı oku", "Düzelt ve test et"],
  "dosyalar": ["src/app.py"],
  "riskler": ["Eski çağrılar bozulabilir"],
  "yapilamayanlar": [
    {"konu": "Dış yayın", "gerekce": "API izin vermiyor", "alternatif": "Taslak hazırla"}
  ],
  "dogrulama": ["pytest çalıştır"]
}
```"""

    plan = parse_teacher_plan(answer)

    assert plan.steps == ("İlgili dosyayı oku", "Düzelt ve test et")
    assert plan.files == ("src/app.py",)
    assert plan.unworkables[0].alternative == "Taslak hazırla"


def test_eksik_adimli_plan_reddedilir() -> None:
    with pytest.raises(TeacherPlanError):
        parse_teacher_plan(
            '{"adimlar": [], "dosyalar": [], "riskler": [], "yapilamayanlar": [], "dogrulama": []}'
        )


def test_son_denetimin_somut_bulgulari_ayristirilir() -> None:
    assert parse_teacher_review('{"bulgular": ["Yetkili istek testi eksik"]}') == (
        "Yetkili istek testi eksik",
    )


def test_belirsiz_denetim_temiz_sayilmaz() -> None:
    with pytest.raises(TeacherPlanError):
        parse_teacher_review("Sanırım iyi görünüyor")


def test_turkce_anahtar_ve_atlanan_alanlar_plani_dusurmez() -> None:
    """Ölçüldü (29 Ekim): `adımlar` yazan ya da `yapilamayanlar`ı atlayan öğretmen
    `TeacherPlanError` alıyor, ek onarım çağrısı harcanıyordu (A4-11)."""
    plan = parse_teacher_plan(
        '{"adımlar": ["Oku", {"adım": "Düzelt"}], "dosyalar": ["a.py"], "doğrulama": ["pytest"]}'
    )

    assert plan.steps == ("Oku", "Düzelt")
    assert plan.files == ("a.py",)
    assert plan.verification == ("pytest",)
    assert plan.risks == () and plan.unworkables == ()


def test_turkce_yapilamayan_anahtarlari_katlanir() -> None:
    plan = parse_teacher_plan(
        '{"adimlar": ["Oku"], "yapılamayanlar": [{"konu": "x", "gerekçe": "y", "alternatif": "z"}]}'
    )

    assert plan.unworkables[0].reason == "y"


def test_yapisal_olarak_bozuk_alan_hala_reddedilir() -> None:
    with pytest.raises(TeacherPlanError):
        parse_teacher_plan('{"adimlar": ["Oku"], "dosyalar": "a.py"}')
    with pytest.raises(TeacherPlanError):
        parse_teacher_plan('{"adimlar": ["Oku"], "yapilamayanlar": [{"konu": "x"}]}')
