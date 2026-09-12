"""Yerel hesap deposu — SQLite, kullanıcının kendi bilgisayarında.

Ağ yoktur: kayıt da doğrulama da bu dosyada biter. Hesap silinirse ya da
uygulama kaldırılırsa veriyle birlikte gider; bu ürünün açık sözüdür.

Şema tek bir tabloda durur ve `sqlite3` stdlib'dedir — masaüstü paketine yeni
bir bağımlılık girmez.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from ..core.accounts import Account, AccountCreation
from ..core.clock import SystemClock
from ..core.protocols import Clock
from .passwords import (
    PASSWORD_MIN_CHARS,
    generate_recovery_code,
    hash_secret,
    normalize_recovery_code,
    verify_secret,
)

__all__ = ["AccountError", "SqliteAccountStore", "accounts_db_path"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    recovery_hash TEXT NOT NULL,
    avatar        TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL
);
"""


class AccountError(ValueError):
    """Kullanıcıya gösterilebilir hesap hatası."""


def accounts_db_path() -> Path:
    """Hesap veritabanının yolu.

    HESAP DİZİNİNDEN BAĞIMSIZDIR: hesapların listesi hesaba göre değişemez,
    yoksa giriş ekranı kimi listeleyeceğini bilemezdi. Hesaba özel veriler
    (yapılandırma, sağlayıcı oturumları) ayrı dizinlerde durur.
    """
    from ..config.paths import base_config_dir

    return base_config_dir() / "accounts.db"


class SqliteAccountStore:
    """`AccountStore` protokolünün SQLite uygulaması."""

    def __init__(self, path: Path | None = None, *, clock: Clock | None = None) -> None:
        self._path = path or accounts_db_path()
        self._clock = clock or SystemClock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # --- okuma ------------------------------------------------------------- #

    def list_accounts(self) -> tuple[Account, ...]:
        with self._connect() as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                "SELECT id, username, email, avatar, created_at FROM accounts ORDER BY created_at"
            )
            return tuple(_account(row) for row in cursor.fetchall())

    def _find(self, connection: sqlite3.Connection, identifier: str) -> sqlite3.Row | None:
        with closing(connection.cursor()) as cursor:
            cursor.execute(
                "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE "
                "OR email = ? COLLATE NOCASE",
                (identifier.strip(), identifier.strip()),
            )
            row: sqlite3.Row | None = cursor.fetchone()
            return row

    # --- yazma ------------------------------------------------------------- #

    def create(
        self, *, username: str, email: str, password: str, avatar: str = ""
    ) -> AccountCreation:
        """Yeni hesap aç ve kurtarma kodunu BİR KEZ döndür."""
        ad = username.strip()
        posta = email.strip()
        if not ad:
            raise AccountError("Kullanıcı adı boş olamaz.")
        if "@" not in posta or posta.startswith("@") or posta.endswith("@"):
            raise AccountError("Geçerli bir e-posta adresi yaz.")
        if len(password) < PASSWORD_MIN_CHARS:
            raise AccountError(f"Parola en az {PASSWORD_MIN_CHARS} karakter olmalı.")
        kod = generate_recovery_code()
        hesap = Account(
            account_id=uuid.uuid4().hex,
            username=ad,
            email=posta,
            avatar=avatar.strip(),
            created_at=self._clock.now(),
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO accounts (id, username, email, password_hash, recovery_hash, "
                    "avatar, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        hesap.account_id,
                        hesap.username,
                        hesap.email,
                        hash_secret(password),
                        hash_secret(normalize_recovery_code(kod)),
                        hesap.avatar,
                        hesap.created_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            # Hangi alanın çakıştığını söylemek gerekir: "kayıt olmadı" diyen bir
            # mesaj kullanıcıyı kör bırakır.
            alan = "E-posta" if "email" in str(error) else "Kullanıcı adı"
            raise AccountError(f"{alan} zaten kullanılıyor.") from error
        return AccountCreation(account=hesap, recovery_code=kod)

    def authenticate(self, *, identifier: str, password: str) -> Account | None:
        """Kullanıcı adı ya da e-posta + parola ile giriş."""
        with self._connect() as connection:
            row = self._find(connection, identifier)
        if row is None:
            # Parola yine de doğrulanır: var olmayan kullanıcıda hemen dönmek,
            # cevap süresinden hesabın varlığını sızdırır.
            verify_secret(password, hash_secret("bulunmayan-hesap"))
            return None
        return _account(row) if verify_secret(password, row["password_hash"]) else None

    def reset_password(
        self, *, identifier: str, recovery_code: str, new_password: str
    ) -> bool:
        """Kurtarma koduyla parolayı değiştir; kod TEK KULLANIMLIKTIR."""
        if len(new_password) < PASSWORD_MIN_CHARS:
            raise AccountError(f"Parola en az {PASSWORD_MIN_CHARS} karakter olmalı.")
        with self._connect() as connection:
            row = self._find(connection, identifier)
            if row is None or not verify_secret(
                normalize_recovery_code(recovery_code), row["recovery_hash"]
            ):
                return False
            # Kullanılan kod yenisiyle değişir: ele geçen bir kod ikinci kez
            # kullanılamamalı.
            connection.execute(
                "UPDATE accounts SET password_hash = ?, recovery_hash = ? WHERE id = ?",
                (
                    hash_secret(new_password),
                    hash_secret(normalize_recovery_code(generate_recovery_code())),
                    row["id"],
                ),
            )
        return True

    def update_profile(
        self, account_id: str, *, username: str, email: str, avatar: str
    ) -> Account:
        with self._connect() as connection:
            try:
                connection.execute(
                    "UPDATE accounts SET username = ?, email = ?, avatar = ? WHERE id = ?",
                    (username.strip(), email.strip(), avatar.strip(), account_id),
                )
            except sqlite3.IntegrityError as error:
                alan = "E-posta" if "email" in str(error) else "Kullanıcı adı"
                raise AccountError(f"{alan} zaten kullanılıyor.") from error
            with closing(connection.cursor()) as cursor:
                cursor.execute(
                    "SELECT id, username, email, avatar, created_at FROM accounts WHERE id = ?",
                    (account_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise AccountError("Hesap bulunamadı.")
        return _account(row)

    def delete(self, account_id: str) -> bool:
        """Hesabı sil. Hesaba ait DOSYALARI silmek çağıranın işidir."""
        with self._connect() as connection, closing(connection.cursor()) as cursor:
            cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            return cursor.rowcount > 0


def _account(row: sqlite3.Row) -> Account:
    return Account(
        account_id=row["id"],
        username=row["username"],
        email=row["email"],
        avatar=row["avatar"],
        created_at=row["created_at"],
    )
