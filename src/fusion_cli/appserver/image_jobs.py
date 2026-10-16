"""Kalıcı görsel kabulü ile oturuma ait üretim/iptal görevlerini birleştir."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from ..core.image_jobs import IMAGE_JOB_REQUEST_PREFIX, ImageJobConflictError, ImageJobRecord
from ..core.owned_thread import await_owned_thread
from ..core.submission import SubmissionKey, SubmissionReceipt, SubmissionState
from ..memory.image_job_store import ImageJobStore
from .image_job_artifacts import collect_outputs, outputs_current

Render = Callable[[], Awaitable[dict[str, object]]]
_TERMINAL = frozenset(
    {SubmissionState.COMPLETED, SubmissionState.FAILED, SubmissionState.CANCELLED}
)
_LOG = logging.getLogger(__name__)
_MESSAGES = {
    "provider_failed": "Sağlayıcı görsel üretemedi. Bağlantı ve kota durumunu kontrol et.",
    "storage_failed": (
        "Görsel çıktısı veya kalıcı makbuz doğrulanamadı; galeri durumunu kontrol et."
    ),
    "cancelled": "Yerel üretim durduruldu; önceden oluşmuş görseller galeride kalabilir.",
    "ambiguous": (
        "Üretimin sonucu belirsiz. Sağlayıcıyı tekrar çağırmadan önce mevcut çıktıyı kontrol et."
    ),
}


class ImageJobService:
    """İstem veya sır saklamaz; her kabul ve worker'ın tek yaşam döngüsü sahibi."""

    def __init__(self, store: ImageJobStore, directory: Path) -> None:
        self._store = store
        self._directory = directory
        self._closed = False
        self._admissions: set[asyncio.Task[dict[str, object]]] = set()
        self._tasks: dict[SubmissionKey, asyncio.Task[None]] = {}
        self._started: set[SubmissionKey] = set()
        self._cancel_requested: set[SubmissionKey] = set()
        self._lost: set[SubmissionKey] = set()

    async def start(
        self, key: SubmissionKey, fingerprint: str, render: Render
    ) -> dict[str, object]:
        if self._closed:
            return {
                "ok": False,
                "code": "session_closed",
                "metin": "Oturum kapandı; üretim başlatılmadı.",
            }
        admission = asyncio.create_task(self._admit(key, fingerprint, render))
        self._admissions.add(admission)
        admission.add_done_callback(self._admissions.discard)
        # RPC bekleyicisinin kopması kabul edilmiş işi veya kabul transaction'ını
        # iptal etmez. İstemci aynı requestId ile makbuzu tekrar okuyabilir.
        return await asyncio.shield(admission)

    async def _admit(
        self, key: SubmissionKey, fingerprint: str, render: Render
    ) -> dict[str, object]:
        try:
            claim = await self._store.claim_image(key, fingerprint)
            if claim.is_owner:
                if self._closed:
                    await self._save_failure(claim.record.receipt, "cancelled")
                    return await self.status(key)
                # Bu kontrol ile task kayıt otoritesi arasında await yok.
                task = asyncio.create_task(self._run(claim.record.receipt, render))
                self._tasks[key] = task
                task.add_done_callback(lambda done: self._job_done(key, done))
            return await self._payload(claim.record)
        except asyncio.CancelledError:
            # Worker thread kabulü bitirmiş ama bekleyici iptal edilmiş olabilir.
            # Yalnız sahipli worker'ı başlamamış accepted kayıt kapatılabilir;
            # finish_image ayrıca DB owner epoch'unu doğrular.
            try:
                record = await self._store.lookup_image(key)
                if (
                    record is not None
                    and record.receipt.state is SubmissionState.ACCEPTED
                    and key not in self._tasks
                ):
                    await self._save_failure(record.receipt, "cancelled")
            except Exception:
                self._lost.add(key)
            raise
        except ImageJobConflictError as error:
            return {"ok": False, "code": "job_conflict", "metin": str(error)}
        except Exception:
            _LOG.error("Görsel işinin kabul deposuna erişilemedi.")
            return {"ok": False, "code": "storage_failed", "metin": _MESSAGES["storage_failed"]}

    async def _save_failure(self, receipt: SubmissionReceipt, code: str) -> None:
        try:
            await self._store.finish_image(
                receipt, state="cancelled" if code == "cancelled" else "failed", error_code=code
            )
        except Exception:
            # Cancel ile tamamlanma commit'i yarıştıysa mevcut terminal gerçek
            # korunur. Yazma başarısı bilinmiyorsa çalışıyor diye sonsuz bekletme.
            try:
                existing = await self._store.lookup_image(receipt.key)
                if existing is not None and existing.receipt.state in _TERMINAL:
                    return
            except Exception:
                pass
            self._lost.add(receipt.key)
            _LOG.error("Görsel işinin terminal makbuzu doğrulanamadı.")

    async def _run(self, receipt: SubmissionReceipt, render: Render) -> None:
        key = receipt.key
        self._started.add(key)
        phase = "starting"
        try:
            if self._closed or key in self._cancel_requested:
                await self._save_failure(receipt, "cancelled")
                return
            await self._store.finish(receipt, state="running")
            if self._closed or key in self._cancel_requested:
                await self._save_failure(receipt, "cancelled")
                return
            phase = "rendering"
            result = await render()
            if key in self._cancel_requested:
                raise asyncio.CancelledError
            if result.get("ok") is not True:
                await self._save_failure(receipt, "provider_failed")
                return
            phase = "validating"
            outputs = await await_owned_thread(collect_outputs, result, self._directory)
            if key in self._cancel_requested:
                raise asyncio.CancelledError
            phase = "committing"
            await self._store.finish_image(receipt, state="completed", outputs=outputs)
        except asyncio.CancelledError:
            await self._save_failure(receipt, "cancelled")
            raise
        except Exception:
            await self._save_failure(
                receipt, "provider_failed" if phase == "rendering" else "storage_failed"
            )

    def _job_done(self, key: SubmissionKey, task: asyncio.Task[None]) -> None:
        if self._tasks.get(key) is task:
            self._tasks.pop(key)
        self._started.discard(key)
        self._cancel_requested.discard(key)
        if not task.cancelled() and task.exception() is not None:
            self._lost.add(key)
            _LOG.error("Görsel worker beklenmeyen biçimde kapandı.")

    async def _payload(self, record: ImageJobRecord) -> dict[str, object]:
        receipt, outputs = record.receipt, record.outputs
        job_id = receipt.key.request_id.removeprefix(IMAGE_JOB_REQUEST_PREFIX)
        if receipt.key in self._lost:
            return {
                "ok": False,
                "jobId": job_id,
                "state": "recoveryRequired",
                "code": "storage_failed",
                "metin": _MESSAGES["storage_failed"],
            }
        if outputs and not await await_owned_thread(outputs_current, outputs, self._directory):
            return {
                "ok": False,
                "jobId": job_id,
                "state": receipt.state.value,
                "code": "artifact_changed",
                "metin": "İşin çıktı dosyası silinmiş veya değişmiş; güncel başarı doğrulanamadı.",
            }
        code = receipt.error_code
        payload: dict[str, object] = {
            "ok": receipt.state
            in {SubmissionState.ACCEPTED, SubmissionState.RUNNING, SubmissionState.COMPLETED},
            "jobId": job_id,
            "state": receipt.state.value,
            "saglayici": outputs[0].provider if outputs else "",
            "dosyalar": [
                {
                    "yol": output.path,
                    "genislik": output.width,
                    "yukseklik": output.height,
                    "sha256": output.digest,
                }
                for output in outputs
            ],
        }
        if receipt.state is SubmissionState.RECOVERY_REQUIRED:
            payload.update(code="ambiguous", metin=_MESSAGES["ambiguous"])
        elif code is not None:
            payload.update(code=code, metin=_MESSAGES.get(code, _MESSAGES["ambiguous"]))
        return payload

    async def status(self, key: SubmissionKey) -> dict[str, object]:
        try:
            record = await self._store.lookup_image(key)
            if record is None:
                return {
                    "ok": False,
                    "code": "job_not_found",
                    "metin": "Bu kapsamda görsel işi bulunamadı.",
                }
            return await self._payload(record)
        except Exception:
            return {"ok": False, "code": "storage_failed", "metin": _MESSAGES["storage_failed"]}

    async def list_jobs(
        self, scope: SubmissionKey, *, after: str = "", limit: int = 20
    ) -> dict[str, object]:
        """Yalnız kayıt özetleri; güncel çıktı otoritesi ayrı durum sorgusundadır."""
        try:
            records, cursor = await self._store.list_images(scope, after=after, limit=limit)
            return {
                "ok": True,
                "isler": [
                    {
                        "jobId": record.receipt.key.request_id.removeprefix(
                            IMAGE_JOB_REQUEST_PREFIX
                        ),
                        "state": record.receipt.state.value,
                        "outputsVerified": False,
                    }
                    for record in records
                ],
                "sonraki": cursor.removeprefix(IMAGE_JOB_REQUEST_PREFIX) if cursor else None,
            }
        except Exception:
            return {"ok": False, "code": "storage_failed", "metin": _MESSAGES["storage_failed"]}

    def _request_cancel(self, key: SubmissionKey, task: asyncio.Task[None]) -> None:
        self._cancel_requested.add(key)
        # Başlamamış coroutine'i cancel etmek finally'yi çalıştırmaz. İlk
        # satırdaki guard kayıtlı işi üretim yapmadan terminale taşır.
        if key in self._started and not task.done() and not task.cancelling():
            task.cancel()

    async def cancel(self, key: SubmissionKey) -> dict[str, object]:
        task = self._tasks.get(key)
        if task is not None:
            self._request_cancel(key, task)
            await asyncio.shield(asyncio.gather(task, return_exceptions=True))
            return await self.status(key)
        result = await self.status(key)
        if result.get("state") in {"accepted", "running"}:
            return {
                **result,
                "ok": False,
                "code": "not_owned",
                "metin": "İş bu canlı oturumun worker'ına bağlı değil; durduruldu sayılmadı.",
            }
        return result

    def stop_accepting(self) -> None:
        """Kapanışın ilk satırında çağrılır; yeni dış etki başlamasını keser."""
        self._closed = True
        for admission in tuple(self._admissions):
            if not admission.done() and not admission.cancelling():
                admission.cancel()
        for key, task in tuple(self._tasks.items()):
            self._request_cancel(key, task)

    async def close(self) -> None:
        self.stop_accepting()
        admissions = tuple(self._admissions)
        if admissions:
            await asyncio.gather(*admissions, return_exceptions=True)
        tasks = tuple(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
