"""Alan adaptörü sözleşmesi — "neyin kanıt sayıldığı" alana göre tanımlanır.

Motor değişmez: plan, kanıt, onay, kurtarma ve bütçe her alanda aynı çalışır. Değişen
şey bir işin BİTTİĞİNİ neyin kanıtladığıdır: Godot'ta "proje açılıyor + hata basmıyor
+ ana sahne diskte"; web'de "sayfanın yerel kaynakları var"; medyada "çıktı dosyası
gerçek".

Adaptör YALNIZ kanıt sözleşmesini tanımlar, akışı tanımlamaz. Her kanca yalnız bir
kök dizin (ya da görev metni) alır ve komut/bulgu/metin döndürür; plan yürütmesine,
onaya veya bütçeye erişimi yoktur. Motorun kurallarını ezmeye başlarsa tek sözleşme
bozulur.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..plan_coverage import Deliverable

#: Kökten engelleyici bulgu üreten denetim; boş demet "sorun yok" demektir.
ArtifactCheck = Callable[[Path], tuple[str, ...]]
#: Kök hakkında evet/hayır cevabı veren ölçüt (ör. "proje çalıştırılabilir mi").
RootPredicate = Callable[[Path], bool]
#: Kapıdan ÖNCE çalışması gereken hazırlık komutlarını üreten kanca.
PreparationCommands = Callable[[Path], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class ToolFailureMarkers:
    """Sıfır çıkış koduna rağmen hatayı ele veren çıktı işaretleri.

    Anahtar ÇALIŞAN ARACIN adıdır, proje işareti değil: motor hatayı basıp `0`
    döndürüyorsa bu, proje dizininde ne olduğundan bağımsız olarak doğrudur.
    """

    tool: str
    markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DomainAdapter:
    """Bir alanın kanıt sözleşmesi."""

    name: str
    #: Bu dizin bu alana ait mi? (kökte varlığı aranan dosya)
    marker: str
    #: Projenin DAVRANIŞINI ölçen kapı komutları.
    gates: tuple[str, ...] = ()
    #: Proje HENÜZ çalıştırılabilir değilken kullanılan ucuz ve dönmesi garanti kapı.
    setup_gates: tuple[str, ...] = ()
    #: Projenin çalıştırılabilir hâle gelip gelmediğini söyleyen ölçüt.
    is_runnable: RootPredicate | None = None
    #: Davranış kapısından önce çalışacak hazırlık komutları.
    preparation: PreparationCommands | None = None
    #: Kapının çalıştırdığı aracın komut satırındaki adı (işaret taraması anahtarı).
    executable: str = ""
    #: Çıkış kodu sıfır olsa bile hatayı ele veren küçük harfli çıktı parçaları.
    output_failure_markers: tuple[str, ...] = ()
    #: Planlayıcıya verilecek, alana özgü kabul koşulları.
    criteria: tuple[str, ...] = ()
    #: Görev metninde bu alanı adıyla anan kelimeler (kelime sınırıyla aranır).
    task_markers: tuple[str, ...] = ()
    #: Kök işareti yokken de artifact denetimini tetikleyen dosya uzantıları.
    artifact_suffixes: tuple[str, ...] = ()
    #: Final kabulde çalışan, motor koşmadan sessiz hatayı söyleyen denetimler.
    artifact_checks: tuple[ArtifactCheck, ...] = ()
    #: Görevde açıkça istenirse planın adıyla karşılaması gereken alan teslimatları.
    deliverables: tuple[Deliverable, ...] = ()

    def matches(self, root: Path) -> bool:
        """Kök dizin bu alanın işaret dosyasını taşıyor mu?"""
        return (root / self.marker).exists()

    def gate_commands(self, root: Path) -> tuple[str, ...]:
        """Projenin AÇILDIĞINI/çalıştığını kanıtlayan komutlar.

        Kapı projenin O ANKİ durumuna göre seçilir. Ölçüldü (7 Eylül canlı koşusu,
        `project-setup`): yarım kurulmuş projede davranış kapısı hatayı basıp ASILI
        KALDI; 120 saniye beklendi, adım zaman aşımıyla düştü ve kurtarma hakkı
        tükendi. Kurulum aşamasında kapı ucuz ve dönmesi GARANTİ olmalı; proje
        çalıştırılabilir olur olmaz yine davranışı ölçer.
        """
        preparation = self.preparation(root) if self.preparation is not None else ()
        if self.is_runnable is None or not self.setup_gates or self.is_runnable(root):
            return preparation + self.gates
        return self.setup_gates

    def zero_exit_failure_markers(self) -> tuple[str, ...]:
        """Çıkış kodu sıfır olsa bile hatayı ele veren çıktı işaretleri."""
        return self.output_failure_markers

    def acceptance_criteria(self) -> tuple[str, ...]:
        """Planlayıcıya verilecek, alana özgü kabul koşulları."""
        return self.criteria

    def is_named_in(self, task: str) -> bool:
        """Görev bu alanı adıyla anıyor mu? Alt-dize değil, kelime eşleşmesi aranır.

        `godot` kelimesi `godotengine` içinde, `html` kelimesi `xhtml` içinde
        EŞLEŞMEZ; `Godot'ta` gibi kesme işaretli Türkçe ekler eşleşir.
        """
        lowered = task.casefold()
        return any(_contains_word(lowered, marker.casefold()) for marker in self.task_markers)

    def applies_to_artifacts(self, root: Path) -> bool:
        """Artifact denetimleri bu kökte çalışmalı mı?

        Kök işareti yokken de alanın dosyaları ağaçta durabilir (ör. `project.godot`
        henüz yazılmamışken sahne ve script). O durumda denetim atlanırsa sessiz
        hata sınıfı teslime kadar gelir.
        """
        if self.matches(root):
            return True
        return any(
            next(root.rglob(f"*{suffix}"), None) is not None for suffix in self.artifact_suffixes
        )

    def artifact_findings(self, root: Path) -> tuple[str, ...]:
        """Alanın artifact denetimlerinin engelleyici bulguları, denetim sırasıyla."""
        if not self.artifact_checks or not self.applies_to_artifacts(root):
            return ()
        return tuple(finding for check in self.artifact_checks for finding in check(root))


def _contains_word(text: str, phrase: str) -> bool:
    """`phrase` metinde iki yanında harf/rakam olmadan geçiyor mu?"""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
