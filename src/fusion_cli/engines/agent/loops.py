"""Döngü primitifleri — her görev aynı ağır akıştan geçmemeli.

Taksonomi çalışmasının bulgusu: bütün ajan mimarileri beş primitifin bileşimidir.
mini-swe-agent'ın ölçümü ise ters yönden aynı şeyi söylüyor: basit görevde sade yol
ağır scaffold kadar iyi, hatta daha iyi — çünkü iskele modelin önüne geçmiyor.

Fusion'ın bugünkü akışı tek parçaydı: her görev planlama, adım doğrulama ve final
kapısından geçiyordu. "Bu dosyada ne var" sorusu için bu, ödenmiş ama karşılığı
alınmamış bir maliyettir.

Bu modül SEÇİMİ tanımlar, akışı değiştirmez: hangi görevin hangi primitif bileşimini
hak ettiğini söyler ve yürütücü buna bakar. Böylece "iskele modelin yolunu kapatmasın"
kuralı yapılandırılabilir bir yere bağlanır.
"""

from __future__ import annotations

from enum import StrEnum

from .classify import TaskKind


class LoopPrimitive(StrEnum):
    """Birleştirilebilir yürütme döngüleri."""

    #: Gözlem–eylem döngüsü. Her akışın tabanı budur.
    REACT = "react"
    #: Planla, adımları sırayla yürüt, adım kanıtını topla.
    PLAN_EXECUTE = "plan_execute"
    #: Hatayı gösteren testi üret, düzelt, testi yeşile çevir.
    GENERATE_TEST_REPAIR = "generate_test_repair"
    #: Aynı adımı birkaç kez dene, kazananı kanıtla seç.
    MULTI_ATTEMPT = "multi_attempt"
    #: Dalları puanlayarak ara; pahalıdır, yalnız açıkça istenirse.
    TREE_SEARCH = "tree_search"


#: Görev türü → primitif bileşimi.
#
# `REACT` her zaman vardır: gözlem-eylem döngüsü olmadan araç kullanılamaz.
# `PLAN_EXECUTE` yalnız çok adımlı işlerde eklenir; keşif ve sohbet bu maliyeti
# ödememelidir. `GENERATE_TEST_REPAIR` hata sınıfına özeldir çünkü kanıtı iki
# parçalıdır (önce kırmızı, sonra yeşil).
_SELECTION: dict[TaskKind, tuple[LoopPrimitive, ...]] = {
    TaskKind.BUGFIX: (
        LoopPrimitive.REACT,
        LoopPrimitive.PLAN_EXECUTE,
        LoopPrimitive.GENERATE_TEST_REPAIR,
    ),
    TaskKind.TEST: (
        LoopPrimitive.REACT,
        LoopPrimitive.PLAN_EXECUTE,
        LoopPrimitive.GENERATE_TEST_REPAIR,
    ),
    TaskKind.FEATURE: (LoopPrimitive.REACT, LoopPrimitive.PLAN_EXECUTE),
    TaskKind.REFACTOR: (LoopPrimitive.REACT, LoopPrimitive.PLAN_EXECUTE),
    TaskKind.WEBSITE: (LoopPrimitive.REACT, LoopPrimitive.PLAN_EXECUTE),
    TaskKind.DOCS: (LoopPrimitive.REACT,),
    TaskKind.EXPLORE: (LoopPrimitive.REACT,),
    TaskKind.GENERAL: (LoopPrimitive.REACT,),
}


def primitives_for(kind: TaskKind) -> tuple[LoopPrimitive, ...]:
    """Bu görev türünün hak ettiği primitif bileşimi."""
    return _SELECTION.get(kind, (LoopPrimitive.REACT,))


def wants_plan(kind: TaskKind) -> bool:
    """Bu görev planlı yürütmeyi hak ediyor mu?"""
    return LoopPrimitive.PLAN_EXECUTE in primitives_for(kind)


def wants_reproduction(kind: TaskKind) -> bool:
    """Bu görevde kanıt iki parçalı mı (önce kırmızı, sonra yeşil)?"""
    return LoopPrimitive.GENERATE_TEST_REPAIR in primitives_for(kind)
