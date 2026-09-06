"""Model yeteneği — bir modelin ne yapabildiğine dair NORMALİZE edilmiş bilgi.

Bu tipler saftır ve üçüncü partiye bağımlı değildir (`core` sözleşmesi). Değerler
UYDURULMAZ: yalnızca elde gerçekten var olan sinyallerden türetilir (model
etiketleri, canlı katalogdan gelen bağlam penceresi). Bilinmeyen bir yetenek
`UNKNOWN`/0/`False` ile temsil edilir — "bilmiyoruz" ayrı bir durumdur ve
uygunluk kararında asla "kesinlikle var" gibi davranılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolSupport(Enum):
    """Bir modelin araç (function/tool) çağırma yeteneği.

    Ayrım davranışsaldır (master prompt §5.3): yalnızca `NATIVE` ve doğrulanmış
    `EMULATED` modeller dosya değiştiren/shell çalıştıran ana agent olabilir;
    `NONE` olan model mutation görevine giremez. `UNKNOWN`, "sağlayıcı söylemedi"
    demektir — gizlenmez ama doğrulanmış da sayılmaz.
    """

    #: Sağlayıcının gerçek function/tool-calling API'si. Fusion bu modeli agent
    #: turunda araçlarla çalıştırır.
    NATIVE = "native"
    #: Araç tanımları prompt'a kontrollü biçimde eklenir; yapılandırılmış çıktı
    #: ayrıştırılır. Eval eşiğini geçmeden mutation görevine giremez.
    EMULATED = "emulated"
    #: Araç desteği yok. Yalnızca sohbet/council/özet rollerinde kullanılabilir.
    NONE = "none"
    #: Doğrulanmamış. Ne var ne yok bilinmiyor; karar ihtiyatlı verilir.
    UNKNOWN = "unknown"


class EditFormat(Enum):
    """Modele sunulacak dosya düzenleme sözleşmesi.

    Ölçüldü (aider): AYNI model, farklı düzenleme biçimiyle %20'den %61'e çıkıyor.
    Search/replace blokları satır numarası ve hunk uzunluğu tutturmayı gerektirmez;
    her değişiklik kendi başına durur ve birindeki hata ötekini geçersiz kılmaz.
    Satır aralığı ise güçlü modelde daha ucuzdur: dosyanın tamamı yeniden yazılmaz.

    Biçimler ÖRTÜŞTÜĞÜ için aynı anda sunulmazlar: dört benzer düzenleme aracını
    birlikte gören zayıf model yanlış olanı seçip turu harcıyor.
    """

    #: `edit_file` / `multi_edit`: eski metin → yeni metin. Zayıf modelin varsayılanı.
    SEARCH_REPLACE = "search_replace"
    #: `replace_range`: satır aralığı ile hedefli değişiklik. Native araç çağıran model.
    LINE_RANGE = "line_range"
    #: Yalnız `write_file`: dosyanın tamamı yeniden yazılır. En dayanıklı, en pahalı.
    WHOLE_FILE = "whole_file"


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Bir modelin uygunluk kararı için gereken normalize yeteneği.

    Alanlar bilinçle azdır: her biri gerçek bir sinyalden türetilebilir ve gerçek
    bir filtreleme kararını besler. Maliyet/gecikme/güvenilirlik burada YOKTUR —
    onlar telemetriden gelir ve router katmanının işidir.
    """

    #: Araç çağırma yeteneği.
    tool_support: ToolSupport = ToolSupport.UNKNOWN
    #: Bağlam penceresi (token). 0 = bilinmiyor.
    context_window: int = 0
    #: Model reasoning/thinking yeteneğini beyan ediyor mu?
    reasoning: bool = False
    #: Görüntü girdisi kabul ediyor mu? Etiketten türetilemez; ihtiyatlı `False`.
    vision: bool = False
