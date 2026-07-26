"""Kullanıcı-local bin dizini PATH'te mi? Değilse doğru komutu göster.

Kurulum "tamam" deyip `fusion` komutu bulunamıyorsa kullanıcı ne olduğunu
anlayamaz. Sebep genellikle tek bir eksik PATH satırıdır.

Bu modül kullanıcının shell yapılandırmasını DEĞİŞTİRMEZ; yalnızca çalıştırılacak
komutu üretir. Habersiz `.zshrc` düzenlemek kurulum betiğinin yapabileceği en
saldırgan şeydir ve geri alması da kullanıcıya kalır.
"""

from __future__ import annotations

import os
from pathlib import PurePath

#: Kabuk adı → (yapılandırma dosyası, PATH ekleme satırı şablonu).
_SHELLS: dict[str, tuple[str, str]] = {
    "zsh": ("~/.zshrc", 'export PATH="{dir}:$PATH"'),
    "bash": ("~/.bashrc", 'export PATH="{dir}:$PATH"'),
    "fish": ("~/.config/fish/config.fish", "fish_add_path {dir}"),
    "sh": ("~/.profile", 'export PATH="{dir}:$PATH"'),
}


def path_hint(
    *, bin_dir: PurePath, path_value: str, shell: str, windows: bool
) -> str | None:
    """Bin dizini PATH'te değilse ne yapılacağını anlatan metin; içindeyse None.

    Karşılaştırma Windows'ta büyük/küçük harf DUYARSIZDIR: duyarlı karşılaştırma
    `C:\\Users\\X` ile `c:\\users\\x` yollarını farklı sayar ve kullanıcıya
    gereksiz bir uyarı gösterirdi.
    """
    ayirac = ";" if windows else os.pathsep
    hedef = str(bin_dir)
    mevcut = [parca for parca in path_value.split(ayirac) if parca]
    if windows:
        if hedef.lower() in {parca.lower() for parca in mevcut}:
            return None
    elif hedef in mevcut:
        return None

    if windows:
        return (
            f"`fusion` komutu PATH'te değil. Bu dizini kalıcı olarak ekle:\n"
            f'    setx PATH "$env:Path;{hedef}"\n'
            f"Sonra PowerShell'i yeniden başlat."
        )

    dosya, sablon = _SHELLS.get(_shell_name(shell), _SHELLS["sh"])
    satir = sablon.format(dir=hedef)
    return (
        f"`fusion` komutu PATH'te değil. Şu satırı {dosya} dosyana ekle:\n"
        f"    {satir}\n"
        f"Sonra yeni bir terminal aç (ya da: source {dosya})."
    )


def _shell_name(shell: str) -> str:
    """`/bin/zsh` → `zsh`. Boş ya da tanınmayan değerde POSIX sh varsayılır."""
    return PurePath(shell).name if shell else "sh"
