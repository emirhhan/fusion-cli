"""Şifreli sır deposu — ortam değişkeni değerlerini (API anahtarı / token) saklar.

Sağlayıcı kimlik bilgileri düz metin config'te tutulmaz. Bu depo onları
`cryptography.Fernet` ile ŞİFRELER, diske öyle yazar ve başlangıçta ortam
değişkeni olarak uygular — böylece LiteLLM ve `keys.detect` onları normal env
değişkeni gibi görür.

Depo, kimlik bilgilerini ORTAM DEĞİŞKENİ ADINA göre saklar (ör. `OPENAI_API_KEY`),
sağlayıcı kimliğine değil. Böylece bu modül `providers` katmanını import etmez
(katman sınırı korunur) ve depo tamamen generic kalır.

Güvenlik modeli:
- Ana anahtar ORTAMDAN gelir (`FUSION_SECRET_KEY`); diske/koda/git'e yazılmaz.
  Şifreli metin ile anahtar hiçbir zaman aynı yerde bulunmaz.
- Anahtar yoksa depo `available=False`; yazma/okuma anlaşılır hata verir, uygulama
  çökmez, uygulama saklanan sır olmadan tam çalışır.
- Değerler ne log'a ne prompt'a ne tool sonucuna girer; yalnızca şifreli dosyada.

Ağır import: `cryptography` yalnızca depo gerçekten kullanılınca yüklenir (RULES).
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import MutableMapping
from pathlib import Path

from ..core.errors import ConfigError


class FernetSecretStore:
    """Ortam değişkeni sırlarını şifreleyerek saklayan depo."""

    def __init__(self, path: Path, *, secret_key: str | None) -> None:
        self._path = path
        self._secret_key = secret_key

    @property
    def available(self) -> bool:
        """Ana anahtar var mı? Yoksa depo kullanılamaz."""
        return self._secret_key is not None

    def _fernet(self) -> object:
        if self._secret_key is None:
            raise ConfigError(
                "Şifreli sır deposu için FUSION_SECRET_KEY ortam değişkeni gerekli. "
                "Güçlü bir değer belirleyip ortamına ekle; anahtar diske yazılmaz."
            )
        from cryptography.fernet import Fernet

        # Kullanıcı ham Fernet anahtarı üretmek zorunda kalmasın: herhangi bir metinden
        # SHA-256 ile 32 baytlık anahtar türetilir.
        derived = base64.urlsafe_b64encode(hashlib.sha256(self._secret_key.encode()).digest())
        return Fernet(derived)

    def _load(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        token = self._path.read_bytes()
        if not token:
            return {}
        from cryptography.fernet import InvalidToken

        try:
            plain = self._fernet().decrypt(token)  # type: ignore[attr-defined]
        except InvalidToken as hata:
            raise ConfigError(
                "Sır deposu çözülemedi: FUSION_SECRET_KEY değişmiş ya da dosya bozuk olabilir."
            ) from hata
        parsed = json.loads(plain.decode())
        return {str(key): str(value) for key, value in parsed.items()}

    def _save(self, data: dict[str, str]) -> None:
        token = self._fernet().encrypt(json.dumps(data).encode())  # type: ignore[attr-defined]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(token)

    def set(self, env_name: str, value: str) -> None:
        """Bir ortam değişkeni sırrını şifreleyip sakla (üzerine yazar)."""
        data = self._load()
        data[env_name] = value
        self._save(data)

    def get(self, env_name: str) -> str | None:
        """Sırrı çöz; yoksa None."""
        return self._load().get(env_name)

    def delete(self, env_name: str) -> bool:
        """Sırrı sil. Vardıysa True."""
        data = self._load()
        if env_name not in data:
            return False
        del data[env_name]
        self._save(data)
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
            if not environ.get(name, "").strip():
                environ[name] = value
                applied.append(name)
        return tuple(applied)
