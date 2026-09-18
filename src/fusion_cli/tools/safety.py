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


def _dot_path(name: str) -> str:
    """Yol bileşeni olarak geçen gizli dizin/dosya: `~/.ssh/x`, `/Users/a/.ssh`, `.ssh`.

    Öncesinde yol ayırıcı ya da kelime sınırı, sonrasında yol ayırıcı ya da bitiş
    aranır; `.sshd_config` gibi başka adlar eşleşmez.
    """
    return rf"(^|[\s'\"=:/]){name}(/|$|[\s'\"])"


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
    # `git -C yol push`, birleşik bayrak (`-uf`) ve `+dal` refspec'i de force push'tur.
    _rule(
        r"\bgit\b[^|;&\n]*\bpush\b[^|;&\n]*\s(--force\b|--force-with-lease\b|"
        r"-[a-zA-Z]*f[a-zA-Z]*\b|\+\S)",
        "uzak geçmişi ezen force push",
    ),
    _rule(
        r"\bgit\b[^|;&\n]*\bpush\b[^|;&\n]*\s(--delete\b|-d\b|--mirror\b|:\S)",
        "uzak dalı/etiketi silen ya da aynalayan push",
    ),
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
    # --- Geri alınamayan dış etkiler (17 Eylül denetimi, F2) ---
    # Yayınlanan paket sürümü geri çekilemez; kayıt defteri aynı sürümü bir daha
    # kabul etmez. `npm publish` zaten sorulurdu ama oturum izniyle hatırlanabiliyordu.
    _rule(
        r"\b(npm|pnpm|yarn|cargo|poetry|flit|hatch|bun)\b[^|;&\n]*\bpublish\b",
        "paketi herkese açık kayıt defterine yayınlama",
    ),
    _rule(r"\btwine\s+upload\b", "paketi herkese açık kayıt defterine yayınlama"),
    _rule(r"\bgem\s+push\b", "paketi herkese açık kayıt defterine yayınlama"),
    _rule(r"\bgh\s+release\s+(create|upload|edit|delete)\b", "GitHub sürümü yayınlama"),
    # Çöp kutusu son kurtarma noktasıdır; boşaltmak silmeyi kalıcı yapar.
    _rule(r"\brm\b[^|;&\n]*\.Trash\b", "çöp kutusunu kalıcı boşaltma"),
    _rule(r"(?i)\bempty\s+(the\s+)?trash\b", "çöp kutusunu kalıcı boşaltma"),
    # --- Sır okuma (17 Eylül denetimi, F1/F2) ---
    # Okunan sır modele, oradan sağlayıcıya gider; sızıntı geri alınamaz. Bu yüzden
    # salt-okur olsa da her kipte sorulur ve oturum iznine dönüşmez.
    _rule(
        r"\bsecurity\s+(dump-keychain|export)\b|"
        r"\bsecurity\s+find-(generic|internet)-password\b[^|;&\n]*\s-[a-zA-Z]*[wg][a-zA-Z]*\b",
        "anahtar zincirinden parola okuma",
    ),
    _rule(r"Library/Keychains\b|\.keychain(-db)?\b", "anahtar zinciri dosyasına erişim"),
    _rule(_dot_path(r"\.ssh"), "SSH anahtarlarına erişim (~/.ssh)"),
    _rule(_dot_path(r"\.aws"), "AWS kimlik bilgilerine erişim (~/.aws)"),
    _rule(_dot_path(r"\.gnupg"), "GPG anahtarlarına erişim (~/.gnupg)"),
    _rule(
        _dot_path(r"\.(netrc|git-credentials)") + r"|\.config/(\S*credentials|gh/hosts\.yml)",
        "düz metin kimlik bilgisi dosyasına erişim",
    ),
    _rule(
        r"Library/(Application.{1,2}Support/(Google/Chrome|Chromium|BraveSoftware|Firefox|"
        r"Microsoft.{1,2}Edge|Arc)|Safari|Cookies)\b|\.mozilla/|"
        r"\.config/(google-chrome|chromium|BraveSoftware)\b",
        "tarayıcı profiline (çerez/parola) erişim",
    ),
    # PROJE İÇİ `.env` bilinçli olarak burada YOK: Fusion kullanıcının kendi
    # projesindeki `.env`i okur ve istendiğinde modele iletir (CLAUDE.md "Sırlar";
    # `read_file` de engellemez). Proje DIŞINDAKİ `.env` başka bir projenin sırrıdır.
    _rule(
        r"(~|\$\{?HOME\}?|\.\.)/(\S*/)?\.env(?![\w-])|(^|[\s'\"=])/\S*/\.env(?![\w-])",
        "proje dışındaki .env dosyasına (sırlar) erişim",
    ),
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
