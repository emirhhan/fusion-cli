"""Olayların tel üzerine çevrilmesi."""

from __future__ import annotations

import dataclasses
import inspect
import io
import json
from collections.abc import Mapping
from enum import Enum
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import pytest

from fusion_cli.appserver.serialize import event_to_dict
from fusion_cli.core import events as E  # noqa: N812
from fusion_cli.core.events import Channel
from fusion_cli.core.types import FusionResult, ModelResult, VerdictSource
from fusion_cli.observability.json_sink import JsonRenderer
from fusion_cli.observability.replay import event_from_payload


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


def test_tool_started_insan_cumlesini_tek_kaynaktan_ekler() -> None:
    """Bkz. bug: araç çalışırken kullanıcıya soluk bir durum satırı gösterilmeli.

    Cümle TEK KAYNAKTAN (`tool_progress.progress_text`) gelir; `event_to_dict`
    bunu `ToolStarted` olayına özel `metin` alanı olarak ekler — arayüz kendi
    çeviri tablosunu tutmaz.
    """
    sonuc = event_to_dict(E.ToolStarted(name="read_file", args={"path": "src/app.py"}))

    assert sonuc["olay"] == "ToolStarted"
    assert sonuc["name"] == "read_file"
    assert sonuc["metin"] == "src/app.py okunuyor"


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


@pytest.mark.parametrize("mutating", [None, False, True])
def test_tool_executed_yeni_opsiyonel_alan_kayitta_geri_kurulur(mutating: bool | None) -> None:
    event = E.ToolExecuted("read_file", {}, E.ToolOutcome.OK, "ok", mutating=mutating)
    assert event_to_dict(event)["mutating"] is mutating
    stream = io.StringIO()
    JsonRenderer(stream).handle(event)
    payload = json.loads(stream.getvalue())
    restored = event_from_payload(payload)
    assert restored == event
    payload.pop("mutating")
    legacy = event_from_payload(payload)
    assert isinstance(legacy, E.ToolExecuted)
    assert legacy.mutating is None


@pytest.mark.parametrize("edit_format", [None, "exact", "whole"])
def test_candidate_started_literal_ve_none_telde_korunur(edit_format: str | None) -> None:
    event = E.CandidateStarted("plan", "step", 1, "model", edit_format, 2, "arm", "task", 1)
    payload = json.loads(json.dumps(event_to_dict(event)))
    assert payload["edit_format"] == edit_format


def test_ic_ice_manifest_dto_telde_yapisini_korur() -> None:
    from fusion_cli.core.prompt_manifest import (
        InstructionMeasurement,
        PromptManifest,
        PromptTransportMeasurement,
    )

    event = E.PromptManifestRecorded(
        PromptManifest(
            10,
            20,
            5,
            35,
            instruction_files=(InstructionMeasurement("repo", "system", 10, 0),),
            transport=PromptTransportMeasurement(35, 30, 5),
        )
    )
    payload = json.loads(json.dumps(event_to_dict(event)))
    assert payload["manifest"]["instruction_files"] == [
        {"label": "repo", "layer": "system", "chars": 10, "trimmed_chars": 0}
    ]
    assert payload["manifest"]["transport"] == {
        "input_chars": 35,
        "sent_chars": 30,
        "trimmed_chars": 5,
        "attachment_chars": 0,
    }
    # Default construction is historical/unknown, never silently relabelled as v2.
    assert payload["manifest"]["measurement_version"] == 1
    assert payload["manifest"]["instructions_location"] == "unknown"
    assert payload["manifest"]["subcomponents_in_system"] is True


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
    origin = get_origin(tip)
    if origin in (Union, UnionType):
        return _deger_uret(next(item for item in get_args(tip) if item is not type(None)))
    if origin is Literal:
        return get_args(tip)[0]
    if isinstance(tip, type) and dataclasses.is_dataclass(tip):
        return _ornek_uret(tip)
    if origin is tuple:
        return ()
    if origin is dict or origin is Mapping:
        return {}
    if tip is Mapping:
        return {}
    raise AssertionError(f"Örnek değeri tanımsız tip: {tip!r}")
