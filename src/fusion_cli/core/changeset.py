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
from hashlib import sha256
from pathlib import Path
from stat import S_ISREG


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Bir dosyanın değiştirilmeden önceki hâli."""

    path: Path
    #: Dosyanın önceki içeriği; dosya YOKTU ise None (geri alma = silme).
    content: bytes | None

    @property
    def existed(self) -> bool:
        return self.content is not None


@dataclass(frozen=True, slots=True)
class RollbackConflict:
    """Güvenle geri alınamayan yol; ilk anlık görüntüsü kayıtta korunur."""

    path: Path
    reason: str

    @property
    def is_identity_conflict(self) -> bool:
        """Kimlik kanıtı eksik/değişmiş mi; doğrulanmış yazma I/O hatasından ayır."""
        return self.reason != _RESTORE_FAILED


_UNKNOWN_IDENTITY = "Son başarılı ajan yazımının kimliği bilinmiyor; dosya korundu."
_CHANGED_IDENTITY = "Dosya son ajan yazımından sonra değişti; mevcut dosya korundu."
_UNREADABLE_IDENTITY = "Dosya kimliği güvenle okunamadı; mevcut dosya korundu."
_RESTORE_FAILED = "Dosya geri alınamadı; ilk anlık görüntü kayıtta korundu."


@dataclass(slots=True)
class ChangeSet:
    """Bir turda dokunulan dosyalar ve ilk hâlleri.

    Aynı dosya birden çok kez yazılsa bile YALNIZCA İLK anlık görüntü saklanır:
    geri alma turun başına döndürmelidir, bir önceki ara adıma değil.
    """

    _snapshots: dict[Path, Snapshot] = field(default_factory=dict)
    #: Dışarıdan EDİNİLEN yollar; izlenir ama geri alınmaz (bkz. `record_acquired`).
    _acquired: set[Path] = field(default_factory=set)
    _applied: dict[Path, str | None] = field(default_factory=dict)
    _conflicts: tuple[RollbackConflict, ...] = field(default=(), init=False)

    @property
    def conflicts(self) -> tuple[RollbackConflict, ...]:
        """Son geri almada korunan yolların salt okunur çakışma sonucu."""
        return self._conflicts

    def record_applied(self, path: Path) -> None:
        """Başarılı yazma/silme SONRASI kimliği kaydet; okunamıyorsa bilinmez bırak."""
        if path not in self._snapshots:
            return
        self._applied.pop(path, None)
        try:
            self._applied[path] = _identity(path)
        except OSError:
            # Başarısı doğrulanmamış kimlik, geri almada kör yazmaya izin vermez.
            return

    def invalidate_applied(self, path: Path) -> None:
        """Gözlenen değişimin ajan sahipliği kanıtlanamıyorsa son kimliği kaldır."""
        self._applied.pop(path, None)

    def record(self, path: Path) -> bool:
        """Yazmadan önce çağrılır. Aynı yol için ikinci çağrı yok sayılır."""
        if path in self._snapshots:
            return True
        try:
            content: bytes | None = path.read_bytes()
        except FileNotFoundError:
            content = None
        except OSError:
            # İzin yüzünden okunamayan dosya geri alınamaz. Kaydetmemek, yanlış
            # içerikle geri yazmaktan iyidir; `restore` bunu atlar.
            return False
        self._snapshots[path] = Snapshot(path=path, content=content)
        return True

    @property
    def paths(self) -> tuple[Path, ...]:
        """Bu turda dokunulan yollar, kaydedilme sırasıyla."""
        return tuple(self._snapshots)

    @property
    def snapshots(self) -> tuple[Snapshot, ...]:
        """İlk hâllerin salt-okunur görünümü; tur sonu denetimde diff kurulur."""
        return tuple(self._snapshots.values())

    @property
    def restorable_paths(self) -> tuple[Path, ...]:
        """`restore()` çağrılınca geri alınması BEKLENEN yollar (edinilenler hariç).

        `/rewind` başarısız geri almayı buna bakarak sayar; edinilen dosya geri
        alınmadığı için "başarısız" sayılmaz.
        """
        return tuple(path for path in self._snapshots if path not in self._acquired)

    def record_created(self, path: Path) -> None:
        """Yalnız atomik, üzerine yazmayan oluşturma BAŞARILI olduktan sonra çağır.

        Önceden kayıt almak, oluşturma yarışını başka yazıcı kazanırsa onun
        dosyasını geri almada siler. Burada oluşturma başarısını çağıran kanıtlar.
        """
        self._snapshots.setdefault(path, Snapshot(path=path, content=None))
        self.record_applied(path)

    def record_acquired(self, path: Path) -> None:
        """Dışarıdan EDİNİLEN dosyayı kaydet ama geri almaya DAHİL ETME.

        İndirilen bir varlık (asset, arşiv, veri kümesi) agent'ın yazdığı kod
        değildir: içeriğini o üretmedi, yalnız getirdi. Adım düştüğünde onu
        silmek iki maliyet üretir — dosya yeniden indirilir (ağ, süre, kota) ve
        o sırada sağlayıcı oran sınırına takılabilir.

        Ölçüldü (13 Eylül, Godot koşusu): `download_file` Kenney'den 260 KB'lık
        paketi indirdi, adım doğrulaması `assets/player.png` bulamayınca düştü
        ve geri alma indirilen paketi de sildi. Sonraki deneme sıfırdan başladı
        ve kurtarma hakkı bitti — oysa dosya diskte duruyor olsa adım yalnız
        arşivi açmayı deneyecekti.

        Dosya yine de İZLENİR (`paths`, `was_created_this_turn`): kısıtlar ve
        raporlama onu görmeye devam eder; yalnız geri alma ona dokunmaz.
        """
        self._snapshots.setdefault(path, Snapshot(path=path, content=None))
        self._acquired.add(path)

    def was_created_this_turn(self, path: Path) -> bool:
        """Bu dosyayı bu turda agent'ın KENDİSİ mi oluşturdu (öncesinde yoktu)?

        Kullanıcının kodunu toptan yeniden yazmakla, dakikalar önce kendi yazdığı bir
        iskele dosyasını doldurmak aynı risk değildir: ilkinde kaybedilecek bir şey
        vardır, ikincisinde yoktur. Toptan-yazma kısıtı bu ayrımı yapabilmek için
        buraya sorar.
        """
        snapshot = self._snapshots.get(path)
        return snapshot is not None and not snapshot.existed

    def __bool__(self) -> bool:
        return bool(self._snapshots)

    def restore(self, *, protected_paths: frozenset[Path] = frozenset()) -> tuple[Path, ...]:
        """Yalnız son başarılı ajan yazımıyla hâlâ eşleşen dosyaları geri al.

        Bilinmeyen/değişmiş kimlik ve I/O hatasında dosyaya dokunulmaz; çakışma
        ve ilk anlık görüntü korunur. Diğer yollar bağımsız olarak geri alınır.
        Çağıranın korumaya aldığı yollar denenmez; ilk kayıtları aynen tutulur.
        """
        restored: list[Path] = []
        conflicts: list[RollbackConflict] = []
        for path, snapshot in tuple(self._snapshots.items()):
            if path in protected_paths:
                continue
            if path in self._acquired:
                self._snapshots.pop(path)
                self._applied.pop(path, None)
                self._acquired.discard(path)
                continue
            reason = self._restore_problem(snapshot)
            if reason is not None:
                conflicts.append(RollbackConflict(path, reason))
                continue
            restored.append(path)
            self._snapshots.pop(path)
            self._applied.pop(path, None)
        self._conflicts = tuple(conflicts)
        return tuple(restored)

    def _restore_problem(self, snapshot: Snapshot) -> str | None:
        path = snapshot.path
        if path not in self._applied:
            return _UNKNOWN_IDENTITY
        try:
            if _identity(path) != self._applied[path]:
                return _CHANGED_IDENTITY
        except OSError:
            return _UNREADABLE_IDENTITY
        return None if _restore_one(snapshot) else _RESTORE_FAILED

    def commit(self) -> None:
        """Değişiklikleri kalıcı say: kayıt boşaltılır, geri alma imkânı biter."""
        self._snapshots.clear()
        self._acquired.clear()
        self._applied.clear()
        self._conflicts = ()

    def absorb(self, other: ChangeSet) -> None:
        """Alt işlemin ilk hâlini ve en son başarılı yazma kimliğini aktar."""
        if other is self:
            return
        for path, snapshot in other._snapshots.items():
            self._snapshots.setdefault(path, snapshot)
            self._applied.pop(path, None)
            if path in other._applied:
                self._applied[path] = other._applied[path]
        self._acquired |= other._acquired
        self._conflicts = tuple(
            {conflict.path: conflict for conflict in (*self._conflicts, *other._conflicts)}.values()
        )
        other.commit()


def _identity(path: Path) -> str | None:
    """Normal dosyanın SHA-256 kimliği; yokluk None, bağ/tür değişimi hatadır."""
    if any(parent.is_symlink() for parent in path.parents):
        raise OSError("Üst dizin sembolik bağ oldu.")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not S_ISREG(metadata.st_mode):
        raise OSError("Yol normal dosya değil.")
    return sha256(path.read_bytes()).hexdigest()


def _restore_one(snapshot: Snapshot) -> bool:
    try:
        if snapshot.content is None:
            # Dosya turdan ÖNCE yoktu: geri alma onu silmektir.
            snapshot.path.unlink(missing_ok=True)
            return True
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        snapshot.path.write_bytes(snapshot.content)
    except OSError:
        return False
    return True
