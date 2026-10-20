"""ChromaDB erişiminin tek noktası.

`chromadb` import'u AĞIRDIR (onnxruntime dahil ~1s). Bu yüzden modül seviyesinde
değil, gerçekten bellek kullanıldığında yapılır — `fusion version` gibi komutlar
bunun bedelini ödemez.

İstemci dizin başına bir kez kurulur: aynı SQLite dosyasına iki istemci bağlanmak
kilit çakışmasına yol açar.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from ..core.errors import FusionError

#: Kosinüs uzayı: gömme vektörlerinde yön benzerliği büyüklükten önemlidir.
COSINE_SPACE = {"hnsw:space": "cosine"}

#: İstemci açılışının üst sınırı. İki Fusion süreci aynı SQLite dosyasını
#: açtığında ikincisi kilidi bekler; sınırsız beklemek turu sebepsiz dondurur.
#: Bellek bir iyileştirmedir — erişilemiyorsa belleksiz devam etmek doğrudur.
#: 5 sn, normal açılışın (yerelde ~0,2 sn) çok üstünde; yalnız gerçek kilit
#: çakışmasında devreye girer.
CLIENT_OPEN_TIMEOUT_S = 5.0

#: Süreçler arası kilit için en fazla bekleme. Ölçüldü (4 Ekim): paralel dört Fusion
#: süreci (masaüstünde her sekme ayrı süreçtir) aynı chroma.sqlite3'e eşzamanlı
#: yazınca biri ChromaDB'nin Rust çekirdeğinde kilit bekleyip turu SONSUZA KADAR
#: dondurdu. Kilit alınamazsa bellek o çağrıda atlanır; tur sürer.
PROCESS_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.05
#: Kilit alındıktan sonra tek bir ChromaDB çağrısının üst sınırı. Ölçüldü (4 Ekim):
#: kilit altında bile çağrı ChromaDB'nin Rust/sqlx iş parçacıklarında süresiz bekledi.
#: Normal sorgu/ekleme yerelde <1 sn; gömme modeli ilk yüklenirken birkaç sn.
CALL_TIMEOUT_S = 30.0
#: Bu süreçte takıldığı görülen depolar: bir daha denenmez (iş parçacığı birikmesin).
_disabled: set[Path] = set()
_LOCK_FILE = ".fusion-chroma.lock"
_logger = logging.getLogger(__name__)

_clients: dict[Path, Any] = {}
_lock = threading.Lock()


class MemoryUnavailableError(FusionError):
    """Bellek deposuna erişilemedi; çağıran taraf boş belleğe düşebilir."""


def get_client(directory: Path) -> Any:
    """Verilen dizin için kalıcı ChromaDB istemcisi (dizin başına tek örnek)."""
    resolved = directory.expanduser().resolve()
    with _lock:
        client = _clients.get(resolved)
        if client is not None:
            return client
        client = _open_with_timeout(resolved)
        _clients[resolved] = client
        return client


def _open_with_timeout(directory: Path) -> Any:
    """İstemciyi aç; süre aşılırsa kilidi bekleme, anlaşılır hatayla dön.

    Açılış ayrı bir iş parçacığında çalışır: SQLite kilidini bekleyen çağrı
    kesilemez, ama biz onu BEKLEMEYİ bırakabiliriz. Terk edilen iş parçacığı
    daemon havuzundadır ve süreç çıkışını engellemez.
    """
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fusion-memory-open")
    future = executor.submit(_create_client, directory)
    try:
        return future.result(timeout=CLIENT_OPEN_TIMEOUT_S)
    except FutureTimeoutError as exc:
        raise MemoryUnavailableError(
            f"Bellek deposu {CLIENT_OPEN_TIMEOUT_S:.0f} sn içinde açılamadı ({directory}): "
            "büyük olasılıkla başka bir Fusion süreci kilidi tutuyor. "
            "Bu tur belleksiz sürüyor."
        ) from exc
    finally:
        # İş parçacığı hâlâ kilidi bekliyor olabilir; onu beklemeden çık.
        executor.shutdown(wait=False)


def _create_client(directory: Path) -> Any:
    try:
        import chromadb  # ağır import: yalnızca bellek gerçekten kullanılınca
        from chromadb.config import Settings

        directory.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(
            path=str(directory), settings=Settings(anonymized_telemetry=False)
        )
    except Exception as exc:
        raise MemoryUnavailableError(f"Bellek deposu açılamadı ({directory}): {exc}") from exc


def _try_lock(handle: IO[str]) -> bool:
    """Kilidi bekletmeden almayı dener; başkası tutuyorsa `False` verir."""
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: IO[str]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def process_lock(directory: Path, timeout_s: float = PROCESS_LOCK_TIMEOUT_S) -> Iterator[bool]:
    """Depo dizini için süreçler arası özel kilit; alınamazsa `False` verir (bekletmez)."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / _LOCK_FILE).open("a") as handle:
        bitis = time.monotonic() + timeout_s
        while True:
            if _try_lock(handle):
                break
            if time.monotonic() >= bitis:
                yield False
                return
            time.sleep(_LOCK_POLL_S)
        try:
            yield True
        finally:
            _unlock(handle)


#: Kilit alınamadığında yöntemin döndüreceği güvenli boş sonuç (bellek o çağrıda yok).
_EMPTY_RESULTS: dict[str, Callable[[], object]] = {
    "query": lambda: {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]},
    "get": lambda: {"ids": [], "documents": [], "metadatas": []},
    "peek": lambda: {"ids": [], "documents": [], "metadatas": []},
    "count": lambda: 0,
}


class GuardedCollection:
    """ChromaDB koleksiyonu; her çağrı süreçler arası kilit altında çalışır.

    Kilit süresinde alınamazsa çağrı YAPILMAZ: okuma boş sonuç, yazma hiçbir şey
    döner ve uyarı loglanır. Bellek bir iyileştirmedir; turu dondurmamalıdır.
    """

    def __init__(self, collection: Any, directory: Path) -> None:
        self._collection = collection
        self._directory = directory

    def __getattr__(self, name: str) -> Any:
        hedef = getattr(self._collection, name)
        if not callable(hedef):
            return hedef

        def _kilitli(*args: Any, **kwargs: Any) -> Any:
            bos = _EMPTY_RESULTS.get(name)
            if self._directory in _disabled:
                return bos() if bos is not None else None

            def _calistir() -> tuple[bool, Any]:
                with process_lock(self._directory, PROCESS_LOCK_TIMEOUT_S) as alindi:
                    return (True, hedef(*args, **kwargs)) if alindi else (False, None)

            havuz = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fusion-memory-call")
            gelecek = havuz.submit(_calistir)
            try:
                tamam, sonuc = gelecek.result(timeout=CALL_TIMEOUT_S)
            except FutureTimeoutError:
                # Çağrı ChromaDB'nin içinde takıldı: beklemeyi bırak, bu süreçte bu depoyu
                # kapat ki takılan iş parçacıkları birikmesin.
                _disabled.add(self._directory)
                tamam, sonuc = False, None
                _logger.warning(
                    "bellek çağrısı süre aştı; bu süreçte bellek kapatıldı",
                    extra={"islem": name, "dizin": str(self._directory)},
                )
            finally:
                havuz.shutdown(wait=False)
            if tamam:
                return sonuc
            return bos() if bos is not None else None

        return _kilitli


def get_collection(directory: Path, name: str, *, embedding_function: Any = None) -> Any:
    """Koleksiyonu al ya da oluştur (süreçler arası kilitli sarmalayıcıyla)."""
    kwargs: dict[str, Any] = {"name": name, "metadata": COSINE_SPACE}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    resolved = directory.expanduser().resolve()
    try:
        with process_lock(resolved, PROCESS_LOCK_TIMEOUT_S) as alindi:
            if not alindi:
                raise MemoryUnavailableError(
                    f"Bellek deposu kilidi {PROCESS_LOCK_TIMEOUT_S:.0f} sn içinde alınamadı "
                    f"({resolved}); bu tur belleksiz sürüyor."
                )
            koleksiyon = get_client(resolved).get_or_create_collection(**kwargs)
        return GuardedCollection(koleksiyon, resolved)
    except MemoryUnavailableError:
        raise
    except Exception as exc:
        raise MemoryUnavailableError(f"Koleksiyon açılamadı ({name}): {exc}") from exc


def reset_clients() -> None:
    """Önbelleklenmiş istemcileri kapatıp bırak (testler arası izolasyon için)."""
    _disabled.clear()
    with _lock:
        clients = tuple(_clients.values())
        _clients.clear()
    for client in clients:
        close = getattr(client, "close", None)
        if callable(close):
            close()
