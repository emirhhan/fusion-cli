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
        ("README dosyasını oku ve özetle", "basit"),
        ("src/app.py dosyasındaki hatayı düzelt", "orta-buyuk"),
        ("src/app.py içindeki add hatasını düzelt; mevcut testi çalıştır", "orta-buyuk"),
        ("Shopify API ile ürün yayımlama akışını kur ve doğrula", "orta-buyuk"),
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
