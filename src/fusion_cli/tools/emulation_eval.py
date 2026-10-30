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

        # Çağrı hiç ayrıştırılamadıysa şema/argüman metrikleri 1.0 DEĞİL başarısızlıktır
        # (eskiden yalnız `tool_selection` düşüyor, ayrıntı raporu yanıltıyordu). Bozuk
        # argüman JSON'u da istisna değil başarısızlıktır: ölçülmek istenen tam olarak budur.
        gercek = _load_arguments(ilk.arguments) if ilk is not None else None

        if case.schema is not None:
            sema_toplam += 1
            if gercek is not None:
                sema_basari += 0 if validate_arguments(case.schema, gercek) else 1

        if case.expected_arguments is not None:
            arg_toplam += 1
            if gercek is None:
                continue
            # Beklenen her argüman AYNEN korunmalı; şemada geçerli ek isteğe bağlı
            # argüman (ör. `search_code`'a `path: "."`) korunumu bozmaz. Birebir eşitlik
            # istemek geçerli ve doğru çağrıları (Gemini, 18 Ekim 2026: pattern doğru,
            # path ek) başarısız sayıp dosya yazma iznini sebepsiz kapatıyordu.
            arg_basari += (
                1
                if all(
                    anahtar in gercek and gercek[anahtar] == deger
                    for anahtar, deger in case.expected_arguments.items()
                )
                else 0
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
