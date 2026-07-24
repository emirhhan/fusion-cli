"""Yıkıcı komut tespiti.

Otomatik onay modu bile bu kontrolü baypas edemez: burada yakalanan bir komut için
kullanıcıya DAİMA sorulur. Amaç her komutu sorgulamak değil — bu kullanıcıyı yorar
ve onayı anlamsızlaştırır — yalnızca geri alınamaz olanları yakalamaktır.

Desenler tek yerde tanımlıdır ve testlerle kilitlenmiştir; koda dağıtılmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.tools import ToolArgs


@dataclass(frozen=True, slots=True)
class DangerRule:
    """Bir yıkıcı komut deseni ve kullanıcıya gösterilecek gerekçesi."""

    pattern: re.Pattern[str]
    reason: str


def _rule(expression: str, reason: str) -> DangerRule:
    return DangerRule(pattern=re.compile(expression), reason=reason)


#: Tehlikeli kabuk komutu desenleri. Sıra önemsizdir; ilk eşleşen gerekçe gösterilir.
DANGER_RULES: tuple[DangerRule, ...] = (
    _rule(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rf]", "özyinelemeli/zorlamalı dosya silme"),
    _rule(r"\brm\s+-[a-zA-Z]*r", "özyinelemeli dosya silme"),
    _rule(r"\brm\s+-[a-zA-Z]*f\s+.*\*", "joker ile zorlamalı silme"),
    _rule(r":\(\)\s*\{.*\|.*&\s*\}", "fork bomb"),
    _rule(r"\bmkfs\b", "dosya sistemi biçimlendirme"),
    _rule(r"\bdd\s+if=", "ham disk yazma"),
    _rule(r">\s*/dev/sd", "ham diske yönlendirme"),
    _rule(r"\b(shutdown|reboot|halt)\b", "sistemi kapatma/yeniden başlatma"),
    _rule(r"\bchmod\s+-R\s+000\b", "özyinelemeli yetki sıfırlama"),
    _rule(r"\bgit\s+push\b.*(--force|-f)\b", "uzak geçmişi ezen force push"),
    _rule(r"\bgit\s+reset\s+--hard\b", "commit'lenmemiş çalışmayı yok etme"),
    _rule(r"\bgit\s+clean\s+-[a-zA-Z]*f", "izlenmeyen dosyaları kalıcı silme"),
    _rule(r"\bgit\s+checkout\s+--\s+\.", "tüm yerel değişiklikleri geri alma"),
    _rule(r"\b(curl|wget)\b.*\|\s*(sudo\s+)?(ba)?sh\b", "internetten indirilen kodu çalıştırma"),
    # Process substitution ile indirilen kodu çalıştırma: bash <(curl …). Boru
    # yakalamayan bu biçim yukarıdaki desene takılmaz, ayrıca yakalanır.
    _rule(r"<\s*\(\s*(curl|wget)\b", "internetten indirilen kodu çalıştırma"),
    # base64/açık kodu çözüp kabuğa boşaltma: echo … | base64 -d | sh.
    _rule(r"\bbase64\b.*(-d|--decode)\b.*\|\s*(ba)?sh\b", "kodlanmış kodu çözüp çalıştırma"),
    _rule(r"\bsudo\b", "yükseltilmiş yetkiyle çalıştırma"),
    _rule(r"\bkill\s+-9\b", "süreci zorla sonlandırma"),
    _rule(r"\bpkill\b", "ada göre süreç sonlandırma"),
    _rule(r"\b(npm|pip|pip3|yarn|pnpm)\s+.*(uninstall|remove)\b", "paket kaldırma"),
    # find ile toplu silme/komut çalıştırma: -delete ya da -exec rm.
    _rule(r"\bfind\b.*-delete\b", "find ile toplu dosya silme"),
    _rule(r"\bfind\b.*-exec\s+rm\b", "find ile toplu dosya silme"),
    # Python tek-satır ile yıkıcı işlem: python -c "... rmtree/os.system/remove ...".
    _rule(
        r"\bpython[0-9.]*\s+-c\b.*\b(rmtree|os\.system|os\.remove|unlink|subprocess)\b",
        "Python tek-satırıyla yıkıcı işlem",
    ),
    # Dosyayı sıfırlama: truncate -s 0.
    _rule(r"\btruncate\b.*-s\s*0\b", "dosya içeriğini sıfırlama"),
)


def danger_reason(tool_name: str, args: ToolArgs) -> str | None:
    """Bu araç çağrısı yıkıcı mı? Öyleyse gerekçesini döndür, değilse None.

    Şu an yalnızca kabuk komutları denetlenir: dosya yazma/düzenleme geri alınabilir
    (diff önizlemesi gösterilir, sürüm kontrolü kurtarır), kabuk komutu değildir.
    """
    if tool_name != "run_shell":
        return None
    command = args.get("command")
    if not isinstance(command, str):
        return None
    return next((rule.reason for rule in DANGER_RULES if rule.pattern.search(command)), None)


def is_dangerous(tool_name: str, args: ToolArgs) -> bool:
    """Otomatik onay modunda bile kullanıcıya sorulmalı mı?"""
    return danger_reason(tool_name, args) is not None
