"""Adım düzeyinde geri alma — başarısız deneme enkaz bırakmaz.

Uzun otonom koşuda her başarısız deneme diske yarım bir durum bırakırsa, sonraki
deneme kendi hatasıyla değil öncekinin enkazıyla uğraşır. Ölçüldü (6 Eylül Godot
koşusu): adım üç kez denendi, her denemede `main.tscn` kısmen yazıldı ve model
kendi önceki çıktısını "mevcut dosya" sanıp üstüne yazmaya çalıştı; yapı denetimi
her seferinde reddetti ve tur ilerlemeden bitti.

`ChangeSet` zaten her yazmadan ÖNCE dosyanın hâlini saklıyor; buradaki tek iş, o
kaydı adım sınırında doğru yönde kullanmaktır: doğrulanan adımda `keep`, düşen
denemede `discard`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .changeset import ChangeSet


@dataclass(frozen=True, slots=True)
class StepRollback:
    """Bir adımın yazma kaydı üzerinde geri alma/koruma kararı."""

    changes: ChangeSet

    def keep(self) -> None:
        """Adım doğrulandı: çıktı kalıcıdır, geri alma kaydı kapanır."""
        self.changes.commit()

    def discard(self) -> tuple[Path, ...]:
        """Deneme düştü: bu adımda yazılanları ilk hâline döndür.

        Geri alınan yolları döndürür. Kayıt boşaldığı için bir sonraki deneme kendi
        yazmalarını temiz bir kayıtla tutar — iki denemenin kaydı birbirine karışmaz.
        """
        return self.changes.restore()
