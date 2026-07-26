"""Kullanıcı-local bin dizinini PATH'e EKLE — onaylı, idempotent, geri alınabilir.

Kurulum "tamam" deyip `fusion` komutu bulunamıyorsa kullanıcı ne olduğunu
anlayamaz. Sebep tek bir eksik PATH satırıdır ve onu kullanıcıya elle yazdırmak
kurulumu yarım bırakmaktır.

Ama shell yapılandırması kullanıcının kendi alanıdır. Üç kural bu yüzden var:

1. **Onaysız yazılmaz.** `approved=False` iken dosyaya DOKUNULMAZ.
2. **İdempotent.** İkinci çalıştırma aynı satırı tekrar eklemez.
3. **Tanınabilir.** Eklenen blok işaretlenir; kullanıcı neyi sileceğini bilir.

Başarısızlık kurulumu ÇÖKERTMEZ: shell dosyası yazılamıyorsa (salt-okunur, izin)
sebep bildirilir ve kullanıcı komutu elle çalıştırabilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePath

#: Eklenen bloğu tanıtan yorum. Kullanıcı bunu arayarak geri alabilir.
FUSION_MARKER = "# fusion-cli tarafından eklendi"


@dataclass(frozen=True, slots=True)
class PathSetupResult:
    """PATH kurulumunun sonucu — ne yapıldığı AÇIKÇA bildirilir."""

    changed: bool
    config_file: Path | None = None
    line: str = ""
    #: Yazılamadıysa sebebi. Boşsa sorun yok.
    error: str = ""


def ensure_on_path(*, bin_dir: PurePath, config_file: Path, approved: bool) -> PathSetupResult:
    """Bin dizinini shell yapılandırmasına ekle. `approved=False` ise hiçbir şey yapma."""
    satir = _line_for(config_file, bin_dir)
    if not approved:
        return PathSetupResult(changed=False, config_file=config_file, line=satir)

    try:
        mevcut = config_file.read_text(encoding="utf-8") if config_file.exists() else ""
    except OSError as hata:
        return PathSetupResult(changed=False, config_file=config_file, error=str(hata))

    # İdempotanlık: yol zaten geçiyorsa dosyaya dokunulmaz. Satırın birebir aynı
    # olması beklenmez — kullanıcı elle eklemiş olabilir ve onu çoğaltmak yanlış.
    if str(bin_dir) in mevcut:
        return PathSetupResult(changed=False, config_file=config_file, line=satir)

    blok = f"\n{FUSION_MARKER}\n{satir}\n"
    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with config_file.open("a", encoding="utf-8") as dosya:
            dosya.write(blok)
    except OSError as hata:
        return PathSetupResult(changed=False, config_file=config_file, error=str(hata))
    return PathSetupResult(changed=True, config_file=config_file, line=satir)


def _line_for(config_file: Path, bin_dir: PurePath) -> str:
    """Dosyanın ait olduğu kabuğa uygun PATH satırı.

    Fish farklı bir sözdizimi kullanır; ona `export PATH=` yazmak sessizce
    çalışmaz ve kullanıcı sorunun devam ettiğini görür.
    """
    if config_file.name.endswith(".fish") or "fish" in config_file.parts:
        return f"fish_add_path {bin_dir}"
    return f'export PATH="{bin_dir}:$PATH"'
