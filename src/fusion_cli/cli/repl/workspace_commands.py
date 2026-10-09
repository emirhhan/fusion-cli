"""Çalışma alanı komutları: `/cop`, `/trace`, `/add-dir`.

Terminal alt komutlarının (`fusion cop`, `fusion trace`, `--add-dir`) slash
karşılıkları. Slash komutları terminal ve masaüstü uygulamasında AYNI defterden
çalıştığı için bu özellikler iki yüzeyde de tek yerden gelir.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from ...config.paths import trash_dir
from ...observability.trace_store import TraceStore
from ...tools.safe_delete import TRASH_RETENTION_DAYS, DeleteRefusedError, list_trash, restore
from ..trace_command import trace_text
from .state import ReplState

#: `/cop` listesinde gösterilen en fazla girdi; çöp 30 gün tutulur ve uzayabilir.
TRASH_LIST_LIMIT = 20


def trash(state: ReplState, argument: str) -> str:
    """`/cop` — Fusion'ın sildiklerini listele; `/cop geri-al <kimlik>` geri koyar."""
    del state
    eylem, _, kimlik = argument.strip().partition(" ")
    if eylem in ("geri-al", "geri"):
        if not kimlik.strip():
            return "Kullanım: /cop geri-al <kimlik>  (kimlikler için /cop)"
        try:
            yer = restore(trash_dir(), kimlik.strip())
        except DeleteRefusedError as error:
            return str(error)
        return f"Geri alındı: {yer}"
    if eylem:
        return "Kullanım: /cop  ya da  /cop geri-al <kimlik>"
    girdiler = list_trash(trash_dir())
    if not girdiler:
        return "Fusion çöpü boş."
    satirlar = [f"Fusion çöpü ({TRASH_RETENTION_DAYS} gün saklanır, en yeni önce):"]
    for girdi in girdiler[:TRASH_LIST_LIMIT]:
        zaman = datetime.datetime.fromtimestamp(girdi.deleted_at).strftime("%d.%m.%Y %H:%M")
        satirlar.append(f"  {girdi.id}  {zaman}  {girdi.original}")
    if len(girdiler) > TRASH_LIST_LIMIT:
        satirlar.append(f"  … ve {len(girdiler) - TRASH_LIST_LIMIT} girdi daha")
    satirlar.append("Geri koymak için: /cop geri-al <kimlik>")
    return "\n".join(satirlar)


def trace(state: ReplState, argument: str) -> str:
    """`/trace [kimlik|liste]` — bir koşunun neden düştüğünü sayılarla özetle."""
    store = TraceStore(state.config.memory_dir / "traces")
    return trace_text(store, argument.strip() or None)


def add_dir(state: ReplState, argument: str) -> str:
    """`/add-dir <yol>` — proje kökünün yanında bir klasöre daha erişim aç.

    `/add-dir` tek başına açık klasörleri listeler; `/add-dir kaldir <yol>` kapatır.
    Erişim bu oturumla sınırlıdır; diske kalıcı izin yazılmaz.
    """
    eylem, _, kalan = argument.strip().partition(" ")
    if not eylem:
        if not state.extra_roots:
            return "Ek klasör yok. Eklemek için: /add-dir <yol>"
        return "Ek klasörler:\n" + "\n".join(f"  {yol}" for yol in state.extra_roots)
    if eylem in ("kaldir", "kaldır"):
        hedef = _resolve(kalan)
        if hedef is None or hedef not in state.extra_roots:
            return "Bu klasör ek klasörler arasında değil."
        state.extra_roots = tuple(yol for yol in state.extra_roots if yol != hedef)
        return f"Erişim kapatıldı: {hedef}"
    hedef = _resolve(argument)
    if hedef is None or not hedef.is_dir():
        return "Klasör bulunamadı. Tam yolu ver: /add-dir /Users/sen/proje"
    kok = state.root.expanduser().resolve()
    if hedef == kok or kok in hedef.parents:
        return "Bu klasör zaten proje kökünün içinde."
    if hedef in (Path(hedef.anchor), Path.home().resolve()):
        return "Diskin ya da ev dizininin tamamı eklenemez; bir proje klasörü seç."
    if hedef in state.extra_roots:
        return f"Zaten açık: {hedef}"
    state.extra_roots = (*state.extra_roots, hedef)
    return f"Erişim açıldı (bu oturum için): {hedef}"


def _resolve(text: str) -> Path | None:
    text = text.strip().strip("\"'")
    if not text:
        return None
    try:
        return Path(text).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
