"""Olayların tel üzerine çevrilmesi."""

from __future__ import annotations

import dataclasses
import inspect
import json
from collections.abc import Mapping
from enum import Enum
from typing import Any, get_type_hints

from fusion_cli.appserver.serialize import event_to_dict
from fusion_cli.core import events as E  # noqa: N812
from fusion_cli.core.events import Channel
from fusion_cli.core.types import FusionResult, ModelResult, VerdictSource


def _event_classes() -> list[type[E.Event]]:
    """Modüldeki tüm olay dataclass'ları."""
    return [
        obj
        for _, obj in inspect.getmembers(E, inspect.isclass)
        if dataclasses.is_dataclass(obj) and obj.__module__ == E.__name__ and obj is not E.Event
    ]


def test_sinif_adi_olay_alanina_yazilir() -> None:
    sonuc = event_to_dict(E.TurnFinished())

    assert sonuc["olay"] == "TurnFinished"


def test_alanlar_sozluge_acilir() -> None:
    sonuc = event_to_dict(E.TurnOutcome(status="completed", elapsed_s=1.5))

    assert sonuc["status"] == "completed"
    assert sonuc["elapsed_s"] == 1.5


def test_her_olay_sinifi_json_edilebilir() -> None:
    """Her olay sınıfı temsil edilebilir olmalıdır; yenisi eklenince test kırılır."""
    for cls in _event_classes():
        ornek = _ornek_uret(cls)
        assert ornek is not None, f"{cls.__name__} için test örneği üretilemedi"
        json.dumps(event_to_dict(ornek))


def test_fusion_completed_ozet_sunar() -> None:
    sonuc = event_to_dict(
        E.FusionCompleted(
            FusionResult(
                task="soru",
                task_type="bilgi",
                winner="model",
                final_answer="cevap",
                source=VerdictSource.SINGLE,
                candidates=(
                    ModelResult(name="aday", model="m", text="yanıt", latency_ms=1, ok=True),
                ),
            )
        )
    )

    assert sonuc == {
        "olay": "FusionCompleted",
        "gorev": "soru",
        "gorev_tipi": "bilgi",
        "kazanan": "model",
        "cevap": "cevap",
        "kaynak": "single",
        "aday_sayisi": 1,
    }


def test_model_call_finished_sonucu_yapisal_olarak_serilesir() -> None:
    sonuc = event_to_dict(
        E.ModelCallFinished(
            role="aday",
            result=ModelResult(name="model", model="m", text="yanıt", latency_ms=12, ok=True),
        )
    )

    assert isinstance(sonuc["result"], dict)
    assert sonuc["result"]["name"] == "model"
    assert sonuc["result"]["text"] == "yanıt"


def _ornek_uret(cls: type[E.Event]) -> E.Event:
    """Alanları tiplerine uygun örnek değerlerle doldurup olay üret."""
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        if (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING
        ):
            continue
        kwargs[field.name] = _deger_uret(hints[field.name])
    return cls(**kwargs)


def _deger_uret(tip: Any) -> Any:
    """Test fixture'ı için temel ve iç içe olay alanı değeri üret."""
    if tip is str:
        return "x"
    if tip is float:
        return 0.0
    if tip is int:
        return 0
    if tip is bool:
        return False
    if tip is Channel:
        return Channel.MAIN
    if tip is ModelResult:
        return ModelResult(name="x", model="x", text="x", latency_ms=0, ok=True)
    if tip is FusionResult:
        return FusionResult("x", "x", "x", "x", VerdictSource.SINGLE, ())
    if isinstance(tip, type) and issubclass(tip, Enum):
        return next(iter(tip))
    origin = getattr(tip, "__origin__", None)
    if origin is tuple:
        return ()
    if origin is dict or origin is Mapping:
        return {}
    if tip is Mapping:
        return {}
    raise AssertionError(f"Örnek değeri tanımsız tip: {tip!r}")
