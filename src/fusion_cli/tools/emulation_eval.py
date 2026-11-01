"""Taklit araç çağrısı değerlendirmesi — bir model mutation'a hazır mı?

`ToolSupport.EMULATED` bir model, ancak taklit araç çağrısında yeterince güvenilir
olduğu ÖLÇÜLDÜKTEN sonra dosya değiştiren agent olabilir (master prompt §5.3). Bu
modül, modelin bir dizi senaryodaki çıktısını (önceden toplanmış) puanlar; canlı
model çağrısı YAPMAZ — girdi olarak modelin çıktısını alır, saf ve test edilebilirdir.

Ölçülen dört metrik ve önerilen eşikler §5.3'ten gelir; eşikler yapılandırılabilir.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..core.types import TokenUsage
from ..core.web_provenance import WebResponseProvenance
from .emulation import parse_tool_calls, validate_arguments


@dataclass(frozen=True, slots=True)
class ExpectedCall:
    """Sırası ve bütün argümanları korunması gereken tek çağrı."""

    name: str
    arguments: Mapping[str, object] | None = None
    schema: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class EvalCase:
    """Tek bir değerlendirme senaryosu: modelin çıktısı + beklenen davranış."""

    #: Modelin ürettiği ham çıktı.
    output: str
    #: Beklenen araç adı. `None` ise bu senaryoda HİÇ araç çağrılmamalıdır.
    expected_tool: str | None
    #: Beklenen argümanlar (verilirse birebir eşleşme aranır).
    expected_arguments: Mapping[str, object] | None = None
    #: Aracın function şeması (verilirse argümanlar şemaya karşı doğrulanır).
    schema: Mapping[str, object] | None = None
    expected_calls: tuple[ExpectedCall, ...] | None = None
    case_id: str = ""
    provider: str = "unknown"
    transport: str = "unknown"
    split: str = "diagnostic"
    provenance: str = "synthetic"
    source_id: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    protocol: str = "v1"
    web_provenance: WebResponseProvenance | None = None
    is_admitted: bool = False
    capture_group: str = ""


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Bir modelin taklit araçla mutation yapabilmesi için geçmesi gereken eşikler."""

    tool_selection: float = 0.95
    schema_validity: float = 0.98
    argument_preservation: float = 0.98
    no_false_calls: float = 0.99
    #: Geçmek için en az kaç senaryo ÖLÇÜLMÜŞ olmalı. Ölçüm yokken ya da bir-iki
    #: senaryoda "%100" anlamsızdır (ölçüldü, 30 Ekim: 0 ölçümde 1.0 "geçti" sayılıyordu).
    min_cases: int = 3


@dataclass(frozen=True, slots=True)
class EmulationEvalScore:
    """Değerlendirme sonucu: dört oran [0, 1] ve her birinin ÖLÇÜLEBİLDİĞİ senaryo sayısı.

    Sayaçlar rapor için zorunludur: payda sıfırken oran 1.0 döner ("uygulanamadı"
    cezalandırılmaz) ama bu ekranda "%100" olarak görünür ve ölçülmemiş bir şey
    mükemmel sanılır. Ölçüldü — Gemini hiçbir senaryoda ayrıştırılabilir çağrı
    üretmedi; şema ve argüman metrikleri %100 raporlandı. Şimdi çağrı üretilemeyen
    senaryo bu metriklerde BAŞARISIZLIKTIR (payda şemalı/beklenen argümanlı senaryo
    sayısıdır); sayaç 0 yalnız senaryoda şema/beklenen argüman hiç tanımlı değilse kalır.
    """

    tool_selection: float
    schema_validity: float
    argument_preservation: float
    no_false_calls: float
    #: Her metriğin kaç senaryoda gerçekten ölçülebildiği. 0 = ölçülmedi.
    tool_selection_measured: int = 0
    schema_validity_measured: int = 0
    argument_preservation_measured: int = 0
    no_false_calls_measured: int = 0

    def passes(self, thresholds: Thresholds | None = None) -> bool:
        """Tüm metrikler eşiği geçiyor mu? Eşik verilmezse §5.3 varsayılanları."""
        thresholds = thresholds or DEFAULT_THRESHOLDS
        olculen = self.tool_selection_measured + self.no_false_calls_measured
        if olculen < thresholds.min_cases:
            return False
        return (
            self.tool_selection >= thresholds.tool_selection
            and self.schema_validity >= thresholds.schema_validity
            and self.argument_preservation >= thresholds.argument_preservation
            and self.no_false_calls >= thresholds.no_false_calls
        )


#: §5.3'ün önerdiği varsayılan eşikler. Tek yerde tutulur.
DEFAULT_THRESHOLDS = Thresholds()


def _ratio(basari: int, toplam: int) -> float:
    """Uygulanabilir senaryo yoksa 1.0 (mükemmel): olmayan bir şeyde ceza olmaz."""
    return 1.0 if toplam == 0 else basari / toplam


def _load_arguments(raw: str) -> dict[str, object] | None:
    """Çağrı argümanlarını ayrıştır; bozuk JSON/nesne olmayan değer -> None (başarısızlık)."""
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def score_emulation(cases: Sequence[EvalCase]) -> EmulationEvalScore:
    """Senaryoları puanla: araç seçimi, şema geçerliliği, argüman korunumu, sahte çağrı."""
    secim_basari = secim_toplam = 0
    sema_basari = sema_toplam = 0
    arg_basari = arg_toplam = 0
    sahte_basari = sahte_toplam = 0

    for case in cases:
        parsed = parse_tool_calls(
            case.output,
            protocol=case.protocol,
            provenance=case.web_provenance,
            call_context=case.web_provenance.call_context if case.web_provenance else None,
        )
        expected = case.expected_calls
        if expected is None:
            expected = (
                ()
                if case.expected_tool is None
                else (ExpectedCall(case.expected_tool, case.expected_arguments, case.schema),)
            )
        if not expected:
            sahte_toplam += 1
            sahte_basari += int(not parsed.calls)
            continue
        secim_toplam += 1
        matching = len(parsed.calls) == len(expected) and all(
            call.name == wanted.name for call, wanted in zip(parsed.calls, expected, strict=False)
        )
        matching = matching and not any(warning.blocks_mutation for warning in parsed.warnings)
        secim_basari += int(matching)
        arguments = tuple(_load_arguments(call.arguments) for call in parsed.calls)
        if any(wanted.schema is not None for wanted in expected):
            sema_toplam += 1
            sema_basari += int(
                matching
                and all(
                    actual is not None
                    and (wanted.schema is None or not validate_arguments(wanted.schema, actual))
                    for actual, wanted in zip(arguments, expected, strict=False)
                )
            )
        if any(wanted.arguments is not None for wanted in expected):
            arg_toplam += 1
            arg_basari += int(
                matching
                and all(
                    _arguments_preserved(
                        actual, wanted.arguments, exact=case.expected_calls is not None
                    )
                    for actual, wanted in zip(arguments, expected, strict=False)
                )
            )

    return EmulationEvalScore(
        tool_selection=_ratio(secim_basari, secim_toplam),
        schema_validity=_ratio(sema_basari, sema_toplam),
        argument_preservation=_ratio(arg_basari, arg_toplam),
        no_false_calls=_ratio(sahte_basari, sahte_toplam),
        tool_selection_measured=secim_toplam,
        schema_validity_measured=sema_toplam,
        argument_preservation_measured=arg_toplam,
        no_false_calls_measured=sahte_toplam,
    )


def _arguments_preserved(
    actual: Mapping[str, object] | None,
    expected: Mapping[str, object] | None,
    *,
    exact: bool,
) -> bool:
    """Eski tek çağrı altküme sözleşmesini, yeni çoklu çağrı birebirliğini koru."""
    if actual is None:
        return False
    if expected is None:
        return True
    if exact:
        return actual == expected
    return all(key in actual and actual[key] == value for key, value in expected.items())


RECORDED_TRAIN_CASES = 160
RECORDED_HOLDOUT_CASES = 40
GENUINE_POSITIVE_CASES = 100
ORIGIN_NEGATIVE_CASES = 200
MAX_RECALL_LOSS_PP = 1.0
PROVENANCE_VALUES = frozenset({"synthetic", "recorded"})
RECORDED_SPLITS = frozenset({"train", "holdout"})


def load_corpus(path: Path, *, require_complete: bool = False) -> tuple[EvalCase, ...]:
    """Mevcut public API'yi tek corpus yükleme hattına yönlendir."""
    from .emulation_corpus import load_corpus as load

    return load(path, require_complete=require_complete)


def _f06_comparison(cases: Sequence[EvalCase]) -> dict[str, object]:
    """Aynı admitted V2 pozitiflerini iki parser ile ölç; V1 kaydını V2 sayma."""
    positives = tuple(
        case
        for case in cases
        if case.is_admitted and case.protocol == "v2" and bool(case.expected_calls)
    )
    v1 = score_emulation(tuple(replace(case, protocol="v1") for case in positives))
    v2 = score_emulation(positives)
    measured = bool(positives)
    loss = round(100 * (v1.tool_selection - v2.tool_selection), 12) if measured else None
    return {
        "positive_cases": len(positives),
        "v1_recall": v1.tool_selection if measured else None,
        "v2_recall": v2.tool_selection if measured else None,
        "recall_loss_pp": loss,
        "max_recall_loss_pp": MAX_RECALL_LOSS_PP,
        "recall_passed": loss <= MAX_RECALL_LOSS_PP if loss is not None else None,
    }


def replay_corpus_report(cases: Sequence[EvalCase]) -> dict[str, object]:
    """Yerel replay oranlarını ölçülen paydalar ve gerçek kayıt açığıyla raporla."""
    from dataclasses import asdict

    score = score_emulation(cases)
    recorded = tuple(case for case in cases if case.is_admitted)
    train = sum(case.split == "train" for case in recorded)
    holdout = sum(case.split == "holdout" for case in recorded)
    comparison = _f06_comparison(recorded)
    positive = sum(case.protocol == "v2" and bool(case.expected_calls) for case in recorded)
    negatives = tuple(case for case in cases if case.protocol == "v2" and case.expected_calls == ())
    negative = len(negatives)
    is_f03_complete = train == RECORDED_TRAIN_CASES and holdout == RECORDED_HOLDOUT_CASES
    is_f06_complete = (
        positive >= GENUINE_POSITIVE_CASES
        and negative >= ORIGIN_NEGATIVE_CASES
        and comparison["recall_passed"] is True
        and score_emulation(negatives).no_false_calls == 1.0
    )
    return {
        "passed": score.passes(),
        "metrics": asdict(score),
        "cases": len(cases),
        "synthetic_cases": sum(case.provenance == "synthetic" for case in cases),
        "unverified_recorded_cases": sum(
            case.provenance == "recorded" and not case.is_admitted for case in cases
        ),
        "genuine_positive_cases": positive,
        "f06_comparison": comparison,
        "missing_genuine_positive_cases": max(0, GENUINE_POSITIVE_CASES - positive),
        "synthetic_negative_cases": sum(
            case.provenance == "synthetic" and case.expected_calls == () for case in cases
        ),
        "missing_origin_negative_cases": max(0, ORIGIN_NEGATIVE_CASES - negative),
        "f03_complete": is_f03_complete,
        "f06_complete": is_f06_complete,
        "complete": is_f03_complete and is_f06_complete,
        "recorded_cases": len(recorded),
        "missing_recorded_cases": RECORDED_TRAIN_CASES + RECORDED_HOLDOUT_CASES - len(recorded),
        "missing_recorded_train": RECORDED_TRAIN_CASES - train,
        "missing_recorded_holdout": RECORDED_HOLDOUT_CASES - holdout,
        "usage_unknown_cases": sum(
            not (case.usage.prompt_measured and case.usage.completion_measured) for case in cases
        ),
        "cost_unknown_cases": sum(not case.usage.cost_known for case in cases),
    }
