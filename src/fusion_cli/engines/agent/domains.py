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

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DomainAdapter:
    """Bir alanın kanıt sözleşmesi."""

    name: str
    #: Bu dizin bu alana ait mi? (varlığı aranan dosya)
    marker: str
    _gates: tuple[str, ...] = field(default_factory=tuple)
    #: Proje HENÜZ çalıştırılabilir değilken kullanılan ucuz kapı.
    _setup_gates: tuple[str, ...] = field(default_factory=tuple)
    #: Projenin çalıştırılabilir hâle gelip gelmediğini söyleyen ölçüt.
    _is_runnable: Callable[[Path], bool] | None = None
    _markers: tuple[str, ...] = field(default_factory=tuple)
    _criteria: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, root: Path) -> bool:
        return (root / self.marker).exists()

    def gate_commands(self, root: Path) -> tuple[str, ...]:
        """Projenin AÇILDIĞINI kanıtlayan komutlar.

        Kapı projenin O ANKİ durumuna göre seçilir. Ölçüldü (7 Eylül canlı koşusu,
        `project-setup`): yarım kurulmuş projede davranış kapısı hatayı basıp
        ASILI KALDI; 120 saniye beklendi, adım zaman aşımıyla düştü ve kurtarma
        hakkı tükendi. Kurulum aşamasında kapı ucuz ve dönmesi GARANTİ olmalı;
        proje çalıştırılabilir olur olmaz yine davranışı ölçer.
        """
        if self._is_runnable is None or not self._setup_gates or self._is_runnable(root):
            return self._gates
        return self._setup_gates

    def zero_exit_failure_markers(self) -> tuple[str, ...]:
        """Çıkış kodu sıfır olsa bile hatayı ele veren çıktı işaretleri."""
        return self._markers

    def acceptance_criteria(self) -> tuple[str, ...]:
        """Planlayıcıya verilecek, alana özgü kabul koşulları."""
        return self._criteria


#: `project.godot` içinde ana sahneyi tanımlayan anahtar.
_MAIN_SCENE = re.compile(r"^\s*run/main_scene\s*=\s*\S")
_SECTION = re.compile(r"^\s*\[")


def godot_has_main_scene(root: Path) -> bool:
    """Godot projesi çalıştırılabilir mi: ana sahne tanımlı mı.

    Bölümsüz yazılmış anahtar SAYILMAZ; Godot da saymaz ve "no main scene
    defined in the project" der (bkz. `core/structured_files.py`).
    """
    try:
        content = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    in_section = False
    for line in content.splitlines():
        if _SECTION.match(line):
            in_section = True
        elif in_section and _MAIN_SCENE.match(line):
            return True
    return False


def godot_adapter() -> DomainAdapter:
    """Godot: motorun kendisi projeyi açabiliyor mu, hata basıyor mu?

    Ölçüldü (5-6 Eylül): Godot bozuk script'te ve çalışma zamanı hatasında `0`
    çıkış kodu verebiliyor; "açıldı" ile "hatasız açıldı" ayrı şeylerdir.
    """
    return DomainAdapter(
        name="godot",
        marker="project.godot",
        _gates=("godot --headless --path . --quit",),
        _setup_gates=("godot --headless --path . --editor --quit",),
        _is_runnable=godot_has_main_scene,
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
