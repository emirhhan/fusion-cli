"""Şifreli sır deposu — ortam değişkeni değerlerini (API anahtarı / token) saklar.

Sağlayıcı kimlik bilgileri düz metin config'te tutulmaz. Bu depo onları
`cryptography.Fernet` ile ŞİFRELER, diske öyle yazar ve başlangıçta ortam
değişkeni olarak uygular — böylece LiteLLM ve `keys.detect` onları normal env
değişkeni gibi görür.

Depo, kimlik bilgilerini ORTAM DEĞİŞKENİ ADINA göre saklar (ör. `OPENAI_API_KEY`),
sağlayıcı kimliğine değil. Böylece bu modül `providers` katmanını import etmez
(katman sınırı korunur) ve depo tamamen generic kalır.

Güvenlik modeli:
- Ana anahtar config.keys tarafından çözülür: ortam değişkeni önceliklidir;
  macOS'ta önce Keychain, olmazsa kullanıcıya özel yerel dosya; diğer sistemlerde
  sistem anahtarlığı kullanılır. Yerel dosya yöntemi aynı kullanıcıya karşı Keychain
  erişim denetimi sağlamaz.
- Dosya biçimi `FSV2` + 16 bayt tuz + Fernet belirteci: şifreleme anahtarı ana anahtardan
  scrypt ile türetilir (L2-27). Eski biçim (tuzsuz tek tur SHA-256, çıplak Fernet
  belirteci) okunur; ilk yazımda ya da `upgrade_format` ile yeni biçime geçilir.
- Anahtar yoksa depo `available=False`; yazma/okuma anlaşılır hata verir, uygulama
  çökmez, uygulama saklanan sır olmadan tam çalışır.
- Değerler ne log'a ne prompt'a ne tool sonucuna girer; yalnızca şifreli dosyada.

Ağır import: `cryptography` yalnızca depo gerçekten kullanılınca yüklenir (RULES).
"""

from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import MutableMapping
from pathlib import Path

from ..core.errors import ConfigError
from .writer import config_lock

_logger = logging.getLogger(__name__)

#: Yeni dosya biçiminin başlığı; eski biçim Fernet belirteci olduğundan `gAAAA` ile başlar.
_V2_MAGIC = b"FSV2"
_SALT_BYTES = 16
_HEADER_BYTES = len(_V2_MAGIC) + _SALT_BYTES
#: scrypt maliyeti: 2**15 * 128 * 8 = 32 MiB bellek, bu makinede ≈60 ms (ölçüldü, 30 Ekim).
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 2**26


def _scrypt_available() -> bool:
    """Bazı Python/OpenSSL derlemelerinde `hashlib.scrypt` yoktur."""
    return hasattr(hashlib, "scrypt")


@functools.lru_cache(maxsize=8)
def _scrypt_fernet_key(secret: str, salt: bytes) -> bytes:
    """Ana anahtardan scrypt ile Fernet anahtarı türet (önbellekli: depo her yenilemede açılır)."""
    raw = hashlib.scrypt(
        secret.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
        maxmem=_SCRYPT_MAXMEM,
    )
    return base64.urlsafe_b64encode(raw)


class FernetSecretStore:
    """Ortam değişkeni sırlarını şifreleyerek saklayan depo."""

    def __init__(self, path: Path, *, secret_key: str | None) -> None:
        self._path = path
        self._secret_key = secret_key

    @property
    def available(self) -> bool:
        """Ana anahtar var mı? Yoksa depo kullanılamaz."""
        return self._secret_key is not None

    def _fernet(self, salt: bytes | None = None) -> object:
        """`salt` verilirse scrypt (yeni biçim), verilmezse eski tuzsuz SHA-256 türetmesi."""
        if self._secret_key is None:
            raise ConfigError(
                "Şifreli sır deposu için FUSION_SECRET_KEY ortam değişkeni gerekli. "
                "Güçlü bir değer belirleyip ortamına ekle; anahtar diske yazılmaz."
            )
        from cryptography.fernet import Fernet

        # Kullanıcı ham Fernet anahtarı üretmek zorunda kalmasın: herhangi bir metinden
        # 32 baytlık anahtar türetilir. Eski dosyalar tuzsuz SHA-256 ile yazılmıştı.
        if salt is None:
            return Fernet(
                base64.urlsafe_b64encode(hashlib.sha256(self._secret_key.encode()).digest())
            )
        return Fernet(_scrypt_fernet_key(self._secret_key, salt))

    def _read(self) -> tuple[dict[str, str], bytes | None]:
        """Dosyayı çöz; `(veri, tuz)` döndür. Tuz yeni biçimde dolu, eski/boş dosyada None."""
        if not self._path.is_file():
            return {}, None
        token = self._path.read_bytes()
        if not token:
            return {}, None
        from cryptography.fernet import InvalidToken

        salt: bytes | None = None
        if token.startswith(_V2_MAGIC):
            if len(token) <= _HEADER_BYTES:
                raise ConfigError("Sır deposu içeriği bozuk (başlık eksik).")
            if not _scrypt_available():
                raise ConfigError(
                    "Sır deposu scrypt ile yazılmış ama bu Python derlemesinde hashlib.scrypt yok."
                )
            salt = token[len(_V2_MAGIC) : _HEADER_BYTES]
            token = token[_HEADER_BYTES:]
        try:
            plain = self._fernet(salt).decrypt(token)  # type: ignore[attr-defined]
        except InvalidToken as hata:
            raise ConfigError(
                "Sır deposu çözülemedi: FUSION_SECRET_KEY değişmiş ya da dosya bozuk olabilir."
            ) from hata
        # Çözülen içerik JSON sözlüğü değilse ham `JSONDecodeError`/`AttributeError`
        # `load_config` üzerinden HER komutu çökertirdi; `ConfigError`'a çevrilir (L2-04).
        try:
            parsed = json.loads(plain.decode())
        except (ValueError, UnicodeError) as hata:
            raise ConfigError(
                "Sır deposu içeriği bozuk (JSON okunamadı); önceki sürüm .bak dosyasındadır."
            ) from hata
        if not isinstance(parsed, dict):
            raise ConfigError("Sır deposu içeriği bozuk (sözlük değil).")
        return {str(key): str(value) for key, value in parsed.items()}, salt

    def _load(self) -> dict[str, str]:
        return self._read()[0]

    def _save(self, data: dict[str, str], *, salt: bytes | None = None) -> None:
        """Atomik yaz: geçici dosya + fsync + `os.replace`; öncesinde `.bak` kopyası.

        Doğrudan `write_bytes` yazma sırasında çökmede/disk dolunca dosyayı keserdi ve
        sonraki okuma `InvalidToken` verip TÜM anahtarları kaybettirirdi (L2-04).
        """
        payload = json.dumps(data).encode()
        if _scrypt_available():
            # Mevcut tuz korunur (önbellek isabeti, tek türetme); yeni dosyada rastgele üretilir.
            salt = salt or os.urandom(_SALT_BYTES)
            token = _V2_MAGIC + salt + self._fernet(salt).encrypt(payload)  # type: ignore[attr-defined]
        else:
            token = self._fernet().encrypt(payload)  # type: ignore[attr-defined]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.is_file():
            with contextlib.suppress(OSError):
                shutil.copy2(self._path, self._path.with_name(self._path.name + ".bak"))
        handle, name = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(token)
                stream.flush()
                os.fsync(stream.fileno())
            # Windows veya kısıtlı dosya sistemlerinde şifreleme yine koruma sağlar.
            with contextlib.suppress(OSError):
                temporary.chmod(0o600)
            temporary.replace(self._path)
        except OSError as hata:
            temporary.unlink(missing_ok=True)
            raise ConfigError(f"Sır deposu yazılamadı ({self._path}): {hata}") from hata

    def set(self, env_name: str, value: str) -> None:
        """Bir ortam değişkeni sırrını şifreleyip sakla (üzerine yazar).

        Oku-değiştir-yaz süreçler arası kilitlidir: CLI ile masaüstü aynı anda
        eklerse biri ötekini ezmez.
        """
        with config_lock(self._path):
            data, salt = self._read()
            data[env_name] = value
            self._save(data, salt=salt)

    def get(self, env_name: str) -> str | None:
        """Sırrı çöz; yoksa None."""
        return self._load().get(env_name)

    def delete(self, env_name: str) -> bool:
        """Sırrı sil. Vardıysa True."""
        with config_lock(self._path):
            data, salt = self._read()
            if env_name not in data:
                return False
            del data[env_name]
            self._save(data, salt=salt)
            return True

    def upgrade_format(self) -> bool:
        """Eski (tuzsuz SHA-256) dosyayı scrypt biçimine taşı; taşındıysa True.

        Yedekli ve idempotenttir: eski bayt dizisi `<ad>.v1` olarak bir kez saklanır
        (varsa dokunulmaz), yeni dosya yazılıp YENİDEN çözülerek doğrulanır, doğrulanamazsa
        eski dosya geri konur. Anahtar yok/yanlış/dosya bozuk ya da zaten yeni biçimdeyse
        hiçbir şey değişmez.
        """
        if not self.available or not _scrypt_available() or not self._path.is_file():
            return False
        # Kilitsiz ön kontrol: her yenilemede çağrılır, çoğu zaman iş yoktur.
        with contextlib.suppress(OSError), self._path.open("rb") as stream:
            if stream.read(len(_V2_MAGIC)) in (_V2_MAGIC, b""):
                return False
        with config_lock(self._path):
            if not self._path.is_file():
                return False
            eski = self._path.read_bytes()
            if not eski or eski.startswith(_V2_MAGIC):
                return False
            try:
                data, _ = self._read()
            except ConfigError:
                return False
            yedek = self._path.with_name(self._path.name + ".v1")
            try:
                if not yedek.exists():
                    shutil.copy2(self._path, yedek)
                self._save(data)
                if self._read()[0] != data:
                    raise ConfigError("doğrulanamadı")
            except (OSError, ConfigError):
                with contextlib.suppress(OSError):
                    self._path.write_bytes(eski)
                _logger.warning("Sır deposu yeni biçime taşınamadı; eski dosya korunuyor.")
                return False
            return True

    def list_names(self) -> tuple[str, ...]:
        """Saklanan ortam değişkeni adları (DEĞERLER döndürülmez)."""
        return tuple(sorted(self._load()))

    def apply_to_environ(self, environ: MutableMapping[str, str]) -> tuple[str, ...]:
        """Saklanan sırları ortama uygula. ZATEN DOLU olan değişkene dokunulmaz:
        kullanıcının açıkça verdiği env değeri her zaman kazanır. Uygulanan adları döndür."""
        if not self.available:
            return ()
        applied: list[str] = []
        for name, value in self._load().items():
            # Browser-session cookies are encrypted generic secrets, not environment
            # variables.  Exporting them would expose a full web login to every child
            # process and could exceed platform environment limits.
            if name.startswith("WEB_SECRET::"):
                continue
            if not environ.get(name, "").strip():
                environ[name] = value
                applied.append(name)
        return tuple(applied)
