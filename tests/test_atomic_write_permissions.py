"""Fusion'ın yazdığı dosya, komşularıyla aynı izni taşır.

Ölçüldü: kullanıcının Next.js projesinde Fusion'ın dokunduğu dosyalar
`-rw-------`, komşuları `-rw-r--r--` idi. Sebep `atomic_write`: `mkstemp`
dosyayı bilinçli olarak 0600 açıyor ve `os.replace` bu izni hedefe taşıyordu.

Bu görünmez bir yan etkidir: git izin değişikliğini kayda geçirir ve dosya
başka bir kullanıcıyla çalışan bir derleme/servis tarafından okunamaz hale
gelebilir. Kullanıcı böyle bir değişiklik istemedi.
"""

from __future__ import annotations

import os
from pathlib import Path

from fusion_cli.tools.files import DEFAULT_FILE_MODE, atomic_write


def _izin(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_var_olan_dosyanin_izni_korunur(tmp_path: Path) -> None:
    hedef = tmp_path / "ayarlar.json"
    hedef.write_text("{}", encoding="utf-8")
    hedef.chmod(0o644)

    atomic_write(hedef, '{"a": 1}')

    assert _izin(hedef) == 0o644
    assert hedef.read_text(encoding="utf-8") == '{"a": 1}'


def test_calistirilabilir_dosyanin_izni_korunur(tmp_path: Path) -> None:
    """Betiğin çalıştırma biti düşerse proje sessizce bozulur."""
    hedef = tmp_path / "kur.sh"
    hedef.write_text("#!/bin/sh\n", encoding="utf-8")
    hedef.chmod(0o755)

    atomic_write(hedef, "#!/bin/sh\necho merhaba\n")

    assert _izin(hedef) == 0o755


def test_yeni_dosya_umask_ile_suzulmus_izin_alir(tmp_path: Path) -> None:
    """Kabuktan `touch` ile aynı sonuç: 0666 & ~umask."""
    onceki = os.umask(0o022)
    try:
        hedef = tmp_path / "yeni.txt"
        atomic_write(hedef, "selam")

        assert _izin(hedef) == DEFAULT_FILE_MODE & ~0o022 == 0o644
    finally:
        os.umask(onceki)


def test_yeni_dosya_dar_umaskta_dar_izin_alir(tmp_path: Path) -> None:
    """Kullanıcı umask'ı sıkıysa ona uyulur; izin GENİŞLETİLMEZ."""
    onceki = os.umask(0o077)
    try:
        hedef = tmp_path / "gizli.txt"
        atomic_write(hedef, "selam")

        assert _izin(hedef) == 0o600
    finally:
        os.umask(onceki)


def test_umask_geri_yazilir(tmp_path: Path) -> None:
    """İzin okumak için umask sıfırlanıyor; süreç ayarı bozulmamalı."""
    onceki = os.umask(0o027)
    try:
        atomic_write(tmp_path / "x.txt", "x")
        simdiki = os.umask(0o027)

        assert simdiki == 0o027
    finally:
        os.umask(onceki)
