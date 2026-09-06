"""Alan adaptörleri — "neyin kanıt sayıldığı" alana göre tanımlanır.

Motor değişmez: plan, kanıt, kurtarma ve bütçe her alanda aynı çalışır. Değişen
şey, bir işin BİTTİĞİNİ neyin kanıtladığıdır. Godot'ta "proje açılıyor + hata
basmıyor + ana sahne tanımlı"; bir web uygulamasında "sayfa yükleniyor + kritik
akış tıklanıyor"; veri işinde "şema doğruluyor".

Bugün bu bilgi motorun içine dağılmıştı: keşif tablosunda bir satır, sıfır-çıkış
işaretleri başka dosyada, tanı ayrıştırıcısı üçüncüde. Yeni bir alan eklemek üç
yere dokunmak demekti ve hiçbiri diğerinden haberdar değildi.

Adaptör YALNIZ kanıt sözleşmesini tanımlar, akışı tanımlamaz: motorun kurallarını
ezmeye başlarsa tek sözleşme bozulur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DomainAdapter:
    """Bir alanın kanıt sözleşmesi."""

    name: str
    #: Bu dizin bu alana ait mi? (varlığı aranan dosya)
    marker: str
    _gates: tuple[str, ...] = field(default_factory=tuple)
    _markers: tuple[str, ...] = field(default_factory=tuple)
    _criteria: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, root: Path) -> bool:
        return (root / self.marker).exists()

    def gate_commands(self) -> tuple[str, ...]:
        """Projenin AÇILDIĞINI kanıtlayan komutlar."""
        return self._gates

    def zero_exit_failure_markers(self) -> tuple[str, ...]:
        """Çıkış kodu sıfır olsa bile hatayı ele veren çıktı işaretleri."""
        return self._markers

    def acceptance_criteria(self) -> tuple[str, ...]:
        """Planlayıcıya verilecek, alana özgü kabul koşulları."""
        return self._criteria


def godot_adapter() -> DomainAdapter:
    """Godot: motorun kendisi projeyi açabiliyor mu, hata basıyor mu?

    Ölçüldü (5-6 Eylül): Godot bozuk script'te ve çalışma zamanı hatasında `0`
    çıkış kodu verebiliyor; "açıldı" ile "hatasız açıldı" ayrı şeylerdir.
    """
    return DomainAdapter(
        name="godot",
        marker="project.godot",
        _gates=("godot --headless --path . --quit",),
        _markers=("script error", "parse error", "can't run project", "failed to load script"),
        _criteria=(
            "project.godot içinde ana sahne (run/main_scene) tanımlı",
            "godot --headless çalıştığında hiçbir SCRIPT ERROR / Parse Error basılmıyor",
            "sahnedeki düğüm tipi, bağlı script'in kullandığı API ile uyumlu",
        ),
    )


def web_adapter() -> DomainAdapter:
    """Web: sayfa gerçekten yükleniyor ve konsolda hata yok."""
    return DomainAdapter(
        name="web",
        marker="index.html",
        _criteria=(
            "sayfa tarayıcıda hatasız yükleniyor",
            "konsolda hata yok",
            "kritik kullanıcı akışı tıklanabiliyor",
        ),
    )


#: Kayıtlı adaptörler. Yeni alan eklemek buraya bir satır eklemektir.
_ADAPTERS = (godot_adapter, web_adapter)


def adapter_for(root: Path) -> DomainAdapter | None:
    """Bu proje bir alana ait mi? Değilse `None` — motor genel davranışta kalır."""
    for uret in _ADAPTERS:
        adaptor = uret()
        if adaptor.matches(root):
            return adaptor
    return None
