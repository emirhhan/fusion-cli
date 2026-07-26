"""Bir turda yapılan dosya değişikliklerinin kaydı ve geri alınması.

`multi_edit` kendi içinde atomiktir ama GÖREV atomik değildir: agent A dosyasını
değiştirip B'yi oluşturduktan sonra tur bozulursa yarım bir durum kalır ve
kullanıcı hangi dosyanın agent'a ait olduğunu bilemez.

Bu modül her yazma ÖNCESİNDE dosyanın o anki hâlini saklar, böylece tur geri
alınabilir. Git'e güvenmek yeterli değildir: proje git olmayabilir, dosyalar
untracked olabilir ve kullanıcının kendi bekleyen değişiklikleri bulunabilir —
`git checkout` onları da silerdi. Kayıt yalnızca AGENT'IN dokunduğu yolları taşır.

Bellekte tutulur, diske yazılmaz: kapsam tek bir oturumdur ve içerik kullanıcının
kaynak kodudur; onu geçici bir dizine kopyalamak yeni bir sızıntı yüzeyi açardı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Bir dosyanın değiştirilmeden önceki hâli."""

    path: Path
    #: Dosyanın önceki içeriği; dosya YOKTU ise None (geri alma = silme).
    content: str | None

    @property
    def existed(self) -> bool:
        return self.content is not None


@dataclass(slots=True)
class ChangeSet:
    """Bir turda dokunulan dosyalar ve ilk hâlleri.

    Aynı dosya birden çok kez yazılsa bile YALNIZCA İLK anlık görüntü saklanır:
    geri alma turun başına döndürmelidir, bir önceki ara adıma değil.
    """

    _snapshots: dict[Path, Snapshot] = field(default_factory=dict)

    def record(self, path: Path) -> None:
        """Yazmadan önce çağrılır. Aynı yol için ikinci çağrı yok sayılır."""
        if path in self._snapshots:
            return
        try:
            content: str | None = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            content = None
        except (OSError, UnicodeDecodeError):
            # Okunamayan dosya (ikili içerik, izin) geri alınamaz. Kaydetmemek,
            # yanlış içerikle geri yazmaktan iyidir; `restore` bunu atlar.
            return
        self._snapshots[path] = Snapshot(path=path, content=content)

    @property
    def paths(self) -> tuple[Path, ...]:
        """Bu turda dokunulan yollar, kaydedilme sırasıyla."""
        return tuple(self._snapshots)

    def __bool__(self) -> bool:
        return bool(self._snapshots)

    def restore(self) -> tuple[Path, ...]:
        """Kaydedilen tüm dosyaları ilk hâline döndür; geri alınanları döndürür.

        Bir dosya geri alınamazsa (silinmiş dizin, izin hatası) diğerleri yine de
        geri alınır: yarım geri alma, hiç geri almamaktan iyidir ve hangilerinin
        döndüğü çağırana bildirilir.
        """
        geri_alinan: list[Path] = []
        for snapshot in self._snapshots.values():
            if _restore_one(snapshot):
                geri_alinan.append(snapshot.path)
        self._snapshots.clear()
        return tuple(geri_alinan)

    def commit(self) -> None:
        """Değişiklikleri kalıcı say: kayıt boşaltılır, geri alma imkânı biter."""
        self._snapshots.clear()


def _restore_one(snapshot: Snapshot) -> bool:
    try:
        if snapshot.content is None:
            # Dosya turdan ÖNCE yoktu: geri alma onu silmektir.
            snapshot.path.unlink(missing_ok=True)
            return True
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        snapshot.path.write_text(snapshot.content, encoding="utf-8")
    except OSError:
        return False
    return True
