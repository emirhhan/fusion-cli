"""Büyük araç çıktısını bağlamdan çıkarıp diske alan artifact deposu.

Sessiz kırpma bilgiyi yok ediyordu: model uzun bir test çıktısında gerçek hatayı
hiç görmeden ilerleyebiliyordu (`truncate_notice` bunu en azından söylüyor ama
içeriği geri getirmiyor). Artifact yolu üçüncü seçeneği verir: bağlam küçülür,
içerik KAYBOLMAZ ve model gerektiğinde dosyayı açar.

Context rot ölçülmüş bir olgudur — bağlam uzadıkça, ilgili bilgi hâlâ oradayken
bile doğruluk düşer. Bu yüzden karar "kırp mı, koy mu" değil, "nereye koy".

`core` katmanındadır ve saf tutulur: yalnız dosya sistemi kullanır, olay/konsol
bilmez.
"""

from __future__ import annotations

import re
from pathlib import Path

from .redaction import redact

#: Modele gösterilecek baş kısım: hangi çıktının geldiğini anlamaya yeter.
PREVIEW_CHARS = 2_000
_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


class ArtifactStore:
    """Bir oturumun büyük çıktılarının yazıldığı dizin."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._counter = 0

    @property
    def root(self) -> Path:
        return self._root

    def write(self, name: str, content: str) -> Path:
        """İçeriği maskeleyerek yaz ve yolunu döndür.

        Maskeleme burada yapılır çünkü artifact DİSKTE kalır: transcript, iz ve
        checkpoint ile aynı sözleşme geçerlidir — sır diske düşmez.
        """
        self._root.mkdir(parents=True, exist_ok=True)
        self._counter += 1
        path = self._root / f"{self._counter:03d}-{_SAFE.sub('-', name)}.txt"
        path.write_text(redact(content), encoding="utf-8")
        return path


def offload_output(
    output: str,
    *,
    store: ArtifactStore | None,
    tool: str,
    limit: int,
) -> tuple[str, Path | None]:
    """Sınırı aşan çıktıyı artifact'a al; modele özet ve yol bırak.

    Depo yoksa ya da yazılamıyorsa çıktı olduğu gibi döner: teşhis kolaylığı işin
    kendisini durdurmaz.
    """
    if store is None or len(output) <= limit:
        return output, None
    try:
        path = store.write(tool, output)
    except OSError:
        return output, None
    satir = len(output.splitlines())
    ozet = (
        f"{output[:PREVIEW_CHARS]}\n\n"
        f"[… çıktının tamamı {satir} satır / {len(output)} karakter. Bağlamı şişirmemek "
        f"için dosyaya alındı: {path}\n"
        f'Gerekirse read_file ile aç: read_file(path="{path}").]'
    )
    return ozet, path
