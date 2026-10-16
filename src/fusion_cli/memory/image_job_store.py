"""Görsel makbuzunu mevcut gönderim SQLite transaction'ına bağlayan adaptör."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace

from ..core.image_jobs import (
    IMAGE_JOB_REQUEST_PREFIX,
    ImageJobClaim,
    ImageJobConflictError,
    ImageJobRecord,
    ImageOutputReceipt,
    valid_digest,
)
from ..core.owned_thread import await_owned_thread
from ..core.submission import SubmissionClaim, SubmissionKey, SubmissionReceipt, SubmissionState
from .submission_store import SubmissionStore

_MAX_OUTPUTS = 16
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_ERROR_CODES = frozenset({"provider_failed", "cancelled", "storage_failed", "ambiguous"})


def _outputs(raw: str) -> tuple[ImageOutputReceipt, ...]:
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) > _MAX_OUTPUTS:
            raise ValueError
        fields = set(ImageOutputReceipt.__dataclass_fields__)
        if any(not isinstance(value, dict) or set(value) != fields for value in values):
            raise ValueError
        parsed = tuple(ImageOutputReceipt(**value) for value in values)
        if len({item.path for item in parsed}) != len(parsed):
            raise ValueError
        return parsed
    except (ValueError, TypeError, KeyError):
        raise ImageJobConflictError("Görsel çıktı makbuzu bozuk; üretim tekrarlanmadı.") from None


class ImageJobStore(SubmissionStore):
    """Aynı DB, sahiplik epoch'u ve kabul anahtarı; ikinci görev otoritesi yok."""

    def _claim_transaction(self, key: SubmissionKey) -> SubmissionClaim:
        if key.request_id.startswith(IMAGE_JOB_REQUEST_PREFIX):
            raise ImageJobConflictError("Görsel namespace'i yalnız görsel kabulü için ayrılmıştır.")
        return super()._claim_transaction(key)

    def _retry_transaction(self, key: SubmissionKey) -> SubmissionClaim:
        if key.request_id.startswith(IMAGE_JOB_REQUEST_PREFIX):
            raise ImageJobConflictError("Görsel işi agent görevi olarak yeniden başlatılamaz.")
        return super()._retry_transaction(key)

    def _connect(self) -> sqlite3.Connection:
        connection = super()._connect()
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS image_jobs (profile TEXT, root TEXT, "
                "conversation TEXT, request TEXT, schema_version INTEGER, "
                "input_fingerprint TEXT, outputs TEXT, "
                "PRIMARY KEY(profile,root,conversation,request))"
            )
        except BaseException:
            connection.close()
            raise
        return connection

    def _record(self, connection: sqlite3.Connection, key: SubmissionKey) -> ImageJobRecord | None:
        receipt = self._read(connection, key)
        row = connection.execute(
            "SELECT schema_version,input_fingerprint,outputs FROM image_jobs "
            "WHERE profile=? AND root=? AND conversation=? AND request=?",
            self._values(key),
        ).fetchone()
        if row is None and receipt is None:
            return None
        if row is None or receipt is None:
            raise ImageJobConflictError("Görsel kabulü ile çıktı metadata'sı eşleşmiyor.")
        schema, fingerprint, outputs = row
        if schema != 1 or not valid_digest(fingerprint):
            raise ImageJobConflictError("Görsel iş metadata sürümü veya parmak izi geçersiz.")
        parsed = _outputs(outputs)
        if receipt.state is SubmissionState.COMPLETED and not parsed:
            raise ImageJobConflictError("Tamamlandı kaydında görsel çıktı makbuzu bulunamadı.")
        return ImageJobRecord(receipt, fingerprint, parsed)

    def _lookup_image(self, key: SubmissionKey) -> ImageJobRecord | None:
        with closing(self._connect()) as connection, connection:
            return self._record(connection, key)

    async def lookup_image(self, key: SubmissionKey) -> ImageJobRecord | None:
        return await await_owned_thread(self._lookup_image, key)

    def _list_images(
        self, scope: SubmissionKey, after: str, limit: int
    ) -> tuple[tuple[ImageJobRecord, ...], str | None]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ImageJobConflictError("Görsel iş sayfa boyutu geçersiz.")
        if after and not after.startswith(IMAGE_JOB_REQUEST_PREFIX):
            raise ImageJobConflictError("Görsel iş sayfa işareti geçersiz.")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT request FROM image_jobs WHERE profile=? AND root=? "
                "AND conversation=? AND request>? ORDER BY request LIMIT ?",
                (scope.profile_id, scope.root, scope.conversation_id, after, limit + 1),
            ).fetchall()
            records: list[ImageJobRecord] = []
            for (request,) in rows[:limit]:
                record = self._record(connection, replace(scope, request_id=request))
                if record is not None:
                    records.append(record)
            cursor = rows[limit - 1][0] if len(rows) > limit else None
            return tuple(records), cursor

    async def list_images(
        self, scope: SubmissionKey, *, after: str = "", limit: int = 20
    ) -> tuple[tuple[ImageJobRecord, ...], str | None]:
        """Sohbet yeniden açıldığında mevcut işleri oku; sağlayıcı çağrısı yok."""
        return await await_owned_thread(self._list_images, scope, after, limit)

    def _claim_image(self, key: SubmissionKey, fingerprint: str) -> ImageJobClaim:
        if not key.request_id.startswith(IMAGE_JOB_REQUEST_PREFIX):
            raise ImageJobConflictError("Görsel iş kimliğinin namespace'i geçersiz.")
        if not valid_digest(fingerprint):
            raise ImageJobConflictError("Görsel girdi parmak izi geçersiz.")
        with self._lifecycle_lock:
            if self._closed:
                raise ImageJobConflictError("Gönderim deposu kapalı.")
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = self._record(connection, key)
                if existing is not None:
                    if existing.input_fingerprint != fingerprint:
                        raise ImageJobConflictError(
                            "Aynı görsel iş kimliği farklı girdiyle kullanılamaz."
                        )
                    return ImageJobClaim(False, existing)
                claim = self._claim_in_connection(connection, key)
                if not claim.is_owner:
                    raise ImageJobConflictError("Görsel işi taşınan konuşmaya kabul edilemedi.")
                connection.execute(
                    "INSERT INTO image_jobs VALUES (?,?,?,?,1,?,'[]')",
                    (*self._values(key), fingerprint),
                )
                return ImageJobClaim(True, ImageJobRecord(claim.receipt, fingerprint))

    async def claim_image(self, key: SubmissionKey, fingerprint: str) -> ImageJobClaim:
        return await await_owned_thread(self._claim_image, key, fingerprint)

    def _finish(
        self, receipt: SubmissionReceipt, state: str, error_code: str | None
    ) -> SubmissionReceipt:
        with closing(self._connect()) as connection:
            image = connection.execute(
                "SELECT 1 FROM image_jobs WHERE profile=? AND root=? "
                "AND conversation=? AND request=?",
                self._values(receipt.key),
            ).fetchone()
        if image is not None:
            if state != "running":
                raise ImageJobConflictError(
                    "Görsel terminal kaydı çıktı makbuzuyla birlikte yazılmalı."
                )
            return self._finish_image(receipt, state, (), error_code).receipt
        return super()._finish(receipt, state, error_code)

    def _finish_image(
        self,
        receipt: SubmissionReceipt,
        state: str,
        outputs: tuple[ImageOutputReceipt, ...],
        error_code: str | None,
    ) -> ImageJobRecord:
        if state not in _TERMINAL | {"running"} or (
            error_code is not None and error_code not in _ERROR_CODES
        ):
            raise ImageJobConflictError("Görsel işinin terminal sonucu geçersiz.")
        if state == "running" and (outputs or error_code is not None):
            raise ImageJobConflictError("Çalışıyor kaydı henüz çıktı veya hata taşıyamaz.")
        if state == "completed" and error_code is not None:
            raise ImageJobConflictError("Hata kodu taşıyan görsel işi başarılı sayılamaz.")
        encoded = json.dumps([asdict(item) for item in outputs], sort_keys=True, ensure_ascii=False)
        parsed = _outputs(encoded)
        if state == "completed" and not parsed:
            raise ImageJobConflictError("Çıktısız görsel işi tamamlanmış sayılamaz.")
        with self._lifecycle_lock:
            if self._closed:
                raise ImageJobConflictError("Gönderim deposu kapalı.")
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = self._record(connection, receipt.key)
                if existing is None or existing.receipt.attempt_id != receipt.attempt_id:
                    raise ImageJobConflictError("Görsel deneme makbuzu mevcut işle eşleşmiyor.")
                if existing.receipt.state.value in _TERMINAL:
                    if (
                        existing.receipt.state.value == state
                        and existing.outputs == parsed
                        and existing.receipt.error_code == error_code
                    ):
                        return existing
                    raise ImageJobConflictError("Görsel işinin terminal makbuzu değiştirilemez.")
                changed = connection.execute(
                    "UPDATE submissions SET state=?,error=? WHERE profile=? AND root=? "
                    "AND conversation=? AND request=? AND attempt=? AND owner=? "
                    "AND state IN ('accepted','running')",
                    (
                        state,
                        error_code,
                        *self._values(receipt.key),
                        int(receipt.attempt_id.rsplit(":", 1)[1]),
                        self._epoch(),
                    ),
                ).rowcount
                if changed != 1:
                    raise ImageJobConflictError("Görsel işi bu canlı yürütme sahibine ait değil.")
                connection.execute(
                    "UPDATE image_jobs SET outputs=? WHERE profile=? AND root=? "
                    "AND conversation=? AND request=?",
                    (encoded, *self._values(receipt.key)),
                )
                result = self._record(connection, receipt.key)
                assert result is not None
                return result

    async def finish_image(
        self,
        receipt: SubmissionReceipt,
        *,
        state: str,
        outputs: tuple[ImageOutputReceipt, ...] = (),
        error_code: str | None = None,
    ) -> ImageJobRecord:
        return await await_owned_thread(self._finish_image, receipt, state, outputs, error_code)

    @staticmethod
    def _guard_active_images(
        connection: sqlite3.Connection, profile: str, root: str, conversation: str
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM image_jobs i JOIN submissions s ON i.profile=s.profile "
            "AND i.root=s.root AND i.conversation=s.conversation AND i.request=s.request "
            "WHERE i.profile=? AND i.root=? AND i.conversation=? "
            "AND s.state IN ('accepted','running') LIMIT 1",
            (profile, root, conversation),
        ).fetchone():
            raise ImageJobConflictError("Görsel işi sürerken konuşma taşınamaz veya silinemez.")

    def _prepare_move_metadata(
        self,
        connection: sqlite3.Connection,
        profile: str,
        root: str,
        conversation: str,
        target: str,
    ) -> None:
        self._guard_active_images(connection, profile, root, conversation)
        connection.execute(
            "INSERT OR IGNORE INTO image_jobs SELECT profile,?,conversation,request,"
            "schema_version,input_fingerprint,outputs FROM image_jobs "
            "WHERE profile=? AND root=? AND conversation=?",
            (target, profile, root, conversation),
        )
        conflict = connection.execute(
            "SELECT 1 FROM image_jobs s JOIN image_jobs t ON s.profile=t.profile "
            "AND s.conversation=t.conversation AND s.request=t.request "
            "WHERE s.profile=? AND s.root=? AND s.conversation=? AND t.root=? "
            "AND (s.schema_version!=t.schema_version OR s.input_fingerprint!=t.input_fingerprint "
            "OR s.outputs!=t.outputs) LIMIT 1",
            (profile, root, conversation, target),
        ).fetchone()
        if conflict:
            raise ImageJobConflictError("Hedef görsel metadata'sı kaynakla eşleşmiyor.")

    def _delete_metadata(
        self, connection: sqlite3.Connection, profile: str, root: str, conversation: str
    ) -> None:
        self._guard_active_images(connection, profile, root, conversation)
        connection.execute(
            "DELETE FROM image_jobs WHERE profile=? AND root=? AND conversation=?",
            (profile, root, conversation),
        )
