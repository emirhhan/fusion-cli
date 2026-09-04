"""Tekrar korumasının düşen çağrılarda davranışı."""

from __future__ import annotations

from fusion_cli.core.budget import TurnBudget


class _SabitSaat:
    """Testin ilerletmediği saat; bu testler süreyle ilgilenmiyor."""

    def monotonic(self) -> float:
        return 0.0


def _butce() -> TurnBudget:
    return TurnBudget(
        clock=_SabitSaat(),
        max_model_calls=50,
        max_verify_rounds=2,
        max_empty_retries=2,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=3,
    )



def test_dusen_degistirici_cagri_sonradan_yeniden_denenebilir():
    """Düşen bir değiştirici çağrı, engeli kalkınca yeniden denenebilmeli.

    Ölçülen hata: `godot__create_scene` "Not a valid Godot project" ile düştü
    (proje dosyası henüz yoktu). Model `project.godot`'u yazdı, engel kalktı,
    ama aynı çağrı `TOOL_CALL_DUPLICATE` ile engellendi — mesaj "çalışma
    alanında ilgili bir değişiklik olmadı" diyordu, oysa olmuştu.

    Sebep: değiştirici araçların imzası çağa DUYARSIZ. Tekrar koruması
    "bunu ZATEN YAPTIN" demektir; düşen çağrı hiçbir şey yapmamıştır.
    """
    butce = _butce()
    imza = butce.signature("godot__create_scene", '{"path":"main.tscn"}', mutating=True)

    assert butce.count_call(imza) == 0
    butce.note_failed_call(imza)  # çağrı DÜŞTÜ
    assert butce.count_call(imza) == 1, "arada değişiklik yokken tekrar sayılır"

    butce.record_mutation()  # `project.godot` yazıldı: engel kalktı

    assert butce.count_call(imza) == 0, "gerçek ilerlemeden sonra yeniden denenebilmeli"


def test_basarili_degistirici_cagri_tekrar_sayilir():
    """Başarılı yazmanın tekrarı hâlâ tekrardır; koruma kalkmaz."""
    butce = _butce()
    imza = butce.signature("write_file", '{"path":"a.txt"}', mutating=True)

    assert butce.count_call(imza) == 0
    assert butce.count_call(imza) == 1
