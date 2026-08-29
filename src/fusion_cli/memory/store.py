"""ChromaDB erişiminin tek noktası.

`chromadb` import'u AĞIRDIR (onnxruntime dahil ~1s). Bu yüzden modül seviyesinde
değil, gerçekten bellek kullanıldığında yapılır — `fusion version` gibi komutlar
bunun bedelini ödemez.

İstemci dizin başına bir kez kurulur: aynı SQLite dosyasına iki istemci bağlanmak
kilit çakışmasına yol açar.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

from ..core.errors import FusionError

#: Kosinüs uzayı: gömme vektörlerinde yön benzerliği büyüklükten önemlidir.
COSINE_SPACE = {"hnsw:space": "cosine"}

#: İstemci açılışının üst sınırı. İki Fusion süreci aynı SQLite dosyasını
#: açtığında ikincisi kilidi bekler; sınırsız beklemek turu sebepsiz dondurur.
#: Bellek bir iyileştirmedir — erişilemiyorsa belleksiz devam etmek doğrudur.
#: 5 sn, normal açılışın (yerelde ~0,2 sn) çok üstünde; yalnız gerçek kilit
#: çakışmasında devreye girer.
CLIENT_OPEN_TIMEOUT_S = 5.0

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


def get_collection(directory: Path, name: str, *, embedding_function: Any = None) -> Any:
    """Koleksiyonu al ya da oluştur."""
    kwargs: dict[str, Any] = {"name": name, "metadata": COSINE_SPACE}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    try:
        return get_client(directory).get_or_create_collection(**kwargs)
    except MemoryUnavailableError:
        raise
    except Exception as exc:
        raise MemoryUnavailableError(f"Koleksiyon açılamadı ({name}): {exc}") from exc


def reset_clients() -> None:
    """Önbelleklenmiş istemcileri bırak (testler arası izolasyon için)."""
    with _lock:
        _clients.clear()
