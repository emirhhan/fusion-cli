"""ChromaDB erişiminin tek noktası.

`chromadb` import'u AĞIRDIR (onnxruntime dahil ~1s). Bu yüzden modül seviyesinde
değil, gerçekten bellek kullanıldığında yapılır — `fusion version` gibi komutlar
bunun bedelini ödemez.

İstemci dizin başına bir kez kurulur: aynı SQLite dosyasına iki istemci bağlanmak
kilit çakışmasına yol açar.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from ..core.errors import FusionError

#: Kosinüs uzayı: gömme vektörlerinde yön benzerliği büyüklükten önemlidir.
COSINE_SPACE = {"hnsw:space": "cosine"}

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
        client = _create_client(resolved)
        _clients[resolved] = client
        return client


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
