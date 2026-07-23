"""Agent makroları — sık yapılan işleri tek komuta indiren hazır görevler.

Bir makro iki şey yapar: agent motoruna hazır bir görev metni verir ve gerekiyorsa
sistem promptuna bir davranış kipi ekler. Makro çalıştırmak, o metni elle yazmakla
aynı şeydir; sihir yoktur.

Kipler ayrı tutulur çünkü davranışı değiştirirler:

- **goal** — hedefe ulaşana kadar pes etmez, adım sınırı yükselir.
- **grill-me** — kod yazmadan önce gereksinimleri sorularla netleştirir.

Diğer makrolar (bug, commit, review, browser) yalnızca hazır görev metnidir; agent'ın
davranışını değiştirmezler.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Mode(Enum):
    """Makronun sistem promptuna eklediği davranış kipi."""

    NONE = "none"
    GOAL = "goal"
    GRILL = "grill"


@dataclass(frozen=True, slots=True)
class Macro:
    """Hazır bir agent görevi."""

    #: Kullanıcı argümanı yoksa kullanılacak görev metni.
    task: str
    mode: Mode = Mode.NONE
    #: Argüman verildiğinde metne nasıl yerleştirileceği. Boşsa argüman metnin
    #: yerini alır.
    template: str = ""
    #: Kullanıcı argüman vermezse çalıştırılabilir mi?
    argument_required: bool = False

    def build(self, argument: str) -> str:
        """Kullanıcı argümanından çalıştırılacak görev metnini üret."""
        text = argument.strip()
        if not text:
            return self.task
        return self.template.format(argument=text) if self.template else text


GOAL_PROMPT = """<hedef_kipi>
HEDEF KİPİNDESİN. Verilen görevi tamamlayana kadar pes etmek yok.

- Bir araç ya da komut hata verirse farklı bir yol dene: başka bayraklar, başka
  araç, başka yaklaşım. Aynı çağrıyı tekrarlama.
- Kendi başına aşamayacağın bir engel ya da eksik bilgi varsa `ask_user` ile
  kullanıcıdan müdahale iste; sessizce vazgeçme.
- Görev gerçekten bitmeden nihai cevap verme.
</hedef_kipi>"""

GRILL_PROMPT = """<mülakat_kipi>
GEREKSİNİM ANALİZİ KİPİNDESİN. Hemen kod ya da çözüm üretme.

Önce `ask_user` ile kullanıcıyı sorularla netleştir: ne istediğini tam olarak
anlayana, mimari tercihler (veritabanı, çerçeve, biçim) ve sınırlar belirginleşene
kadar sor. Sorular kısa ve tek konulu olsun.

İkna olduğunda asıl işe başla ve neyi neden yaptığını tek cümleyle söyle.
</mülakat_kipi>"""

MODE_PROMPTS = {Mode.GOAL: GOAL_PROMPT, Mode.GRILL: GRILL_PROMPT}

MACROS: dict[str, Macro] = {
    "goal": Macro(
        task="Proje hedefini belirle ve tamamla.",
        mode=Mode.GOAL,
    ),
    "grill-me": Macro(
        task="",
        mode=Mode.GRILL,
        template="Kullanıcı şunu istiyor: '{argument}'",
        argument_required=True,
    ),
    "bug": Macro(
        task="Projeyi ve kodları inceleyerek bir hata bul ve düzelt. Önce hatayı "
        "yeniden üret ya da testle göster, sonra kök nedeni bul, en dar düzeltmeyi "
        "uygula ve testlerle doğrula.",
        template="Şu hatayı bul ve düzelt: {argument}. Önce kök nedeni tespit et, "
        "sonra en dar düzeltmeyi uygula ve doğrula.",
    ),
    "commit": Macro(
        task="`git status` ve `git diff` ile değişiklikleri incele, mantıklı bir "
        "conventional commit mesajı üret ve commit'le. İlgisiz dosyaları ekleme.",
        template="Değişiklikleri incele ve şu bağlamla commit'le: {argument}",
    ),
    "review": Macro(
        task="`git diff` ile mevcut değişiklikleri (staged ve unstaged) oku ve "
        "güvenlik, doğruluk ve mimari açısından ayrıntılı bir code review yap. "
        "Bulguları önem sırasına göre, dosya:satır referanslarıyla ver.",
        template="Şunu code review yap: {argument}. Güvenlik, doğruluk ve mimari "
        "açısından incele, dosya:satır referansı ver.",
    ),
    "browser": Macro(
        task="",
        template="Web'de araştır: {argument}. `web_search` ile ara, `web_fetch` ile "
        "kaynakları oku, bulguları kaynak bağlantılarıyla özetle.",
        argument_required=True,
    ),
}


def get(name: str) -> Macro | None:
    return MACROS.get(name)


def mode_prompt(mode: Mode) -> str:
    """Kipin sistem promptuna eklenecek metni; kip yoksa boş."""
    return MODE_PROMPTS.get(mode, "")
