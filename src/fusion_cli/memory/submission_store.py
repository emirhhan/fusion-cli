"""İçerik tutmayan, SQLite transaction ile tekilleştiren makbuz indeksi."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock

from ..core.submission import SubmissionClaim, SubmissionKey, SubmissionReceipt, SubmissionState
from .submission_owner import SubmissionOwner


class SubmissionStore:
    """Aynı canlı süreçte açılan adaptörler mevcut işi kurtarmaya çevirmez."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lifecycle_lock = RLock()
        self._owned_epoch: str | None = None
        self._closed = False
        self._owner = SubmissionOwner(path.parent / "submission-owners")

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS submissions (profile TEXT, root TEXT, conversation TEXT, "
            "request TEXT, attempt INTEGER, state TEXT, error TEXT, owner TEXT, "
            "PRIMARY KEY(profile,root,conversation,request))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS submission_moves (profile TEXT, "
            "source TEXT, target TEXT, conversation TEXT, PRIMARY KEY(profile,target,conversation))"
        )
        return connection

    def _epoch(self) -> str:
        with self._lifecycle_lock:
            if self._closed:
                raise OSError("Gönderim deposu kapalı.")
            self._owned_epoch = self._owner.epoch()
            return self._owned_epoch

    def _is_owner_alive(self, owner: str) -> bool:
        return self._owner.is_alive(owner)

    async def close(self) -> None:
        """Nesne sahipliğini kapatır; unfinished kayıtlar recoveryRequired okunur."""
        await asyncio.to_thread(self._close_owner)

    def _close_owner(self) -> None:
        with self._lifecycle_lock:
            self._closed = True
            if self._owned_epoch is not None:
                with closing(self._connect()) as connection, connection:
                    connection.execute(
                        "UPDATE submissions SET "
                        "state='cancelled',error='before_execution_failed' "
                        "WHERE owner=? AND state='accepted'",
                        (self._owned_epoch,),
                    )
            self._owner.close()

    @staticmethod
    def _values(key: SubmissionKey) -> tuple[str, str, str, str]:
        return key.profile_id, key.root, key.conversation_id, key.request_id

    def _read(self, connection: sqlite3.Connection, key: SubmissionKey) -> SubmissionReceipt | None:
        row = connection.execute(
            "SELECT attempt,state,error,owner FROM submissions WHERE profile=? AND root=? "
            "AND conversation=? "
            "AND request=?",
            self._values(key),
        ).fetchone()
        if row is None:
            return None
        attempt, state, error, owner = row
        if state in ("accepted", "running") and not self._is_owner_alive(str(owner)):
            state = "recoveryRequired"
            connection.execute(
                "UPDATE submissions SET state=? WHERE profile=? AND root=? AND conversation=? "
                "AND request=? AND attempt=? AND state IN ('accepted','running')",
                (state, *self._values(key), attempt),
            )
        return SubmissionReceipt(key, f"{key.request_id}:{attempt}", SubmissionState(state), error)

    def _lookup(self, key: SubmissionKey) -> SubmissionReceipt | None:
        with closing(self._connect()) as connection, connection:
            return self._read(connection, key)

    async def lookup(self, key: SubmissionKey) -> SubmissionReceipt | None:
        """Mevcut kayıt doğrulama ve busy kontrolünden önce okunur."""
        return await asyncio.to_thread(self._lookup, key)

    def _claim(self, key: SubmissionKey) -> SubmissionClaim:
        with self._lifecycle_lock:
            if self._closed:
                raise OSError("Gönderim deposu kapalı.")
            return self._claim_transaction(key)

    def _claim_transaction(self, key: SubmissionKey) -> SubmissionClaim:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._read(connection, key)
            if existing is not None:
                return SubmissionClaim(False, existing)
            if connection.execute(
                "SELECT 1 FROM submission_moves WHERE profile=? AND target=? AND conversation=?",
                (key.profile_id, key.root, key.conversation_id),
            ).fetchone():
                return SubmissionClaim(
                    False,
                    SubmissionReceipt(
                        key,
                        f"{key.request_id}:1",
                        SubmissionState.RECOVERY_REQUIRED,
                        "move_pending",
                    ),
                )
            connection.execute(
                "INSERT INTO submissions VALUES (?,?,?,?,1,'accepted',NULL,?)",
                (*self._values(key), self._epoch()),
            )
            return SubmissionClaim(
                True, SubmissionReceipt(key, f"{key.request_id}:1", SubmissionState.ACCEPTED)
            )

    async def claim(self, key: SubmissionKey) -> SubmissionClaim:
        """Unique anahtar transaction içinde tek yürütme sahibi üretir."""
        return await asyncio.to_thread(self._claim, key)

    def _finish(
        self, receipt: SubmissionReceipt, state: str, error_code: str | None
    ) -> SubmissionReceipt:
        parsed = SubmissionState(state)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE submissions SET state=?,error=? WHERE profile=? AND root=? "
                "AND conversation=? "
                "AND request=? AND attempt=? AND state IN ('accepted','running')",
                (
                    parsed.value,
                    error_code,
                    *self._values(receipt.key),
                    int(receipt.attempt_id.rsplit(":", 1)[1]),
                ),
            )
            stored = self._read(connection, receipt.key)
            if stored is None:
                raise ValueError("Gönderim kaydı artık mevcut değil.")
            return stored

    async def finish(
        self, receipt: SubmissionReceipt, *, state: str, error_code: str | None = None
    ) -> SubmissionReceipt:
        """Yalnız sabit sonuç kodunu tutar; cevap ve sağlayıcı hatası yazılmaz."""
        return await asyncio.to_thread(self._finish, receipt, state, error_code)

    def _retry(self, key: SubmissionKey) -> SubmissionClaim:
        with self._lifecycle_lock:
            if self._closed:
                raise OSError("Gönderim deposu kapalı.")
            return self._retry_transaction(key)

    def _retry_transaction(self, key: SubmissionKey) -> SubmissionClaim:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._read(connection, key)
            if existing is None or existing.state not in (
                SubmissionState.FAILED,
                SubmissionState.CANCELLED,
            ):
                if existing is None:
                    raise ValueError("Yeniden denenecek gönderim bulunamadı.")
                return SubmissionClaim(False, existing)
            if connection.execute(
                "SELECT 1 FROM submission_moves WHERE profile=? AND target=? AND conversation=?",
                (key.profile_id, key.root, key.conversation_id),
            ).fetchone():
                return SubmissionClaim(False, existing)
            if existing.error_code not in ("no_tool_effect", "before_execution_failed"):
                return SubmissionClaim(False, existing)
            attempt = int(existing.attempt_id.rsplit(":", 1)[1]) + 1
            connection.execute(
                "UPDATE submissions SET attempt=?,state='accepted',error=NULL,owner=? "
                "WHERE profile=? AND root=? AND conversation=? AND request=?",
                (attempt, self._epoch(), *self._values(key)),
            )
            return SubmissionClaim(
                True,
                SubmissionReceipt(
                    key,
                    f"{key.request_id}:{attempt}",
                    SubmissionState.ACCEPTED,
                ),
            )

    async def retry(self, key: SubmissionKey) -> SubmissionClaim:
        """Yalnız açık eylem failed/cancelled görev altında yeni deneme açar."""
        return await asyncio.to_thread(self._retry, key)

    def _prepare_move(self, profile: str, root: str, conversation: str, target: str) -> None:
        # Kaynak korunur: transcript taşıması yarıda kalırsa iki namespace de tekilleşir.
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO submission_moves VALUES (?,?,?,?)",
                (profile, root, target, conversation),
            )
            intent = connection.execute(
                "SELECT source FROM submission_moves WHERE profile=? AND target=? "
                "AND conversation=?",
                (profile, target, conversation),
            ).fetchone()
            if intent is None or intent[0] != root:
                raise ValueError("Hedef başka bir taşıma işlemine ayrılmış.")
            connection.execute(
                "INSERT OR IGNORE INTO submissions "
                "SELECT profile,?,conversation,request,attempt,state,error,owner FROM submissions "
                "WHERE profile=? AND root=? AND conversation=?",
                (target, profile, root, conversation),
            )
            conflict = connection.execute(
                "SELECT 1 FROM submissions s JOIN submissions t ON s.profile=t.profile "
                "AND s.conversation=t.conversation AND s.request=t.request "
                "WHERE s.profile=? AND s.root=? AND s.conversation=? AND t.root=? "
                "AND (s.attempt!=t.attempt OR s.state!=t.state OR s.owner!=t.owner) LIMIT 1",
                (profile, root, conversation, target),
            ).fetchone()
            if conflict is not None:
                raise ValueError("Hedef gönderim metadata'sı kaynakla eşleşmiyor.")

    async def prepare_move(self, profile: str, root: str, conversation: str, target: str) -> None:
        """Transcript görünür olmadan hedefte makbuz korumasını atomik kurar."""
        await asyncio.to_thread(self._prepare_move, profile, root, conversation, target)

    async def move_prepared(self, profile: str, root: str, conversation: str, target: str) -> bool:
        def read() -> bool:
            with closing(self._connect()) as connection:
                return (
                    connection.execute(
                        "SELECT 1 FROM submission_moves WHERE profile=? AND source=? AND "
                        "target=? AND conversation=?",
                        (profile, root, target, conversation),
                    ).fetchone()
                    is not None
                )

        return await asyncio.to_thread(read)

    def _conversation(self, profile: str, root: str, conversation: str, target: str | None) -> None:
        with closing(self._connect()) as connection, connection:
            if target is None:
                connection.execute(
                    "DELETE FROM submissions WHERE profile=? AND root=? AND conversation=?",
                    (profile, root, conversation),
                )
            else:
                connection.execute(
                    "DELETE FROM submission_moves WHERE profile=? AND source=? AND "
                    "target=? AND conversation=?",
                    (profile, root, target, conversation),
                )
                connection.execute(
                    "DELETE FROM submissions WHERE profile=? AND root=? AND conversation=?",
                    (profile, root, conversation),
                )

    async def delete_conversation(self, profile: str, root: str, conversation: str) -> None:
        """Yetkili sohbet silme kalıcı tekilleştirme ömrünü bitirir."""
        await asyncio.to_thread(self._conversation, profile, root, conversation, None)

    async def move_conversation(
        self, profile: str, root: str, conversation: str, target: str
    ) -> None:
        """Aynı profilde taşınan sohbetin metadata namespace'ini taşır."""
        await self.prepare_move(profile, root, conversation, target)
        await asyncio.to_thread(self._conversation, profile, root, conversation, target)
