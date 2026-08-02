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
from dataclasses import dataclass

from .emulation import parse_tool_calls, validate_arguments


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


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Bir modelin taklit araçla mutation yapabilmesi için geçmesi gereken eşikler."""

    tool_selection: float = 0.95
    schema_validity: float = 0.98
    argument_preservation: float = 0.98
    no_false_calls: float = 0.99


@dataclass(frozen=True, slots=True)
class EmulationEvalScore:
    """Değerlendirme sonucu: dört oran [0, 1]."""

    tool_selection: float
    schema_validity: float
    argument_preservation: float
    no_false_calls: float

    def passes(self, thresholds: Thresholds | None = None) -> bool:
        """Tüm metrikler eşiği geçiyor mu? Eşik verilmezse §5.3 varsayılanları."""
        thresholds = thresholds or DEFAULT_THRESHOLDS
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


def score_emulation(cases: Sequence[EvalCase]) -> EmulationEvalScore:
    """Senaryoları puanla: araç seçimi, şema geçerliliği, argüman korunumu, sahte çağrı."""
    secim_basari = secim_toplam = 0
    sema_basari = sema_toplam = 0
    arg_basari = arg_toplam = 0
    sahte_basari = sahte_toplam = 0

    for case in cases:
        parse = parse_tool_calls(case.output)
        ilk = parse.calls[0] if parse.calls else None

        if case.expected_tool is None:
            # Araç beklenmiyor: hiç çağrı üretilmemeli (sahte çağrı yok).
            sahte_toplam += 1
            sahte_basari += 1 if not parse.calls else 0
            continue

        secim_toplam += 1
        dogru_arac = ilk is not None and ilk.name == case.expected_tool
        secim_basari += 1 if dogru_arac else 0

        if ilk is not None and case.schema is not None:
            sema_toplam += 1
            hatalar = validate_arguments(case.schema, json.loads(ilk.arguments))
            sema_basari += 1 if not hatalar else 0

        if ilk is not None and case.expected_arguments is not None:
            arg_toplam += 1
            arg_basari += 1 if json.loads(ilk.arguments) == dict(case.expected_arguments) else 0

    return EmulationEvalScore(
        tool_selection=_ratio(secim_basari, secim_toplam),
        schema_validity=_ratio(sema_basari, sema_toplam),
        argument_preservation=_ratio(arg_basari, arg_toplam),
        no_false_calls=_ratio(sahte_basari, sahte_toplam),
    )
