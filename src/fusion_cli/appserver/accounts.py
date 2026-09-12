"""Hesap RPC'leri — kayıt, giriş, çıkış, kurtarma, silme.

Depo `accounts` katmanındadır; burası yalnız tel üzerindeki sözleşmeyi kurar:
girdiyi doğrular, hata metnini Türkçeleştirir ve PAROLA/KURTARMA KARMASINI hiçbir
yanıta koymaz.

Etkin hesap bir işaretçi dosyada tutulur ve her Fusion süreci açılışta onu okur
(bkz. `accounts.session`). Böylece hesap değiştirmek için süreçler arasında
ortam değişkeni taşımak gerekmez.
"""

from __future__ import annotations

from typing import Any

from ..accounts import (
    AccountError,
    SqliteAccountStore,
    activate_account,
    adopt_legacy_config,
    clear_active_account,
    forget_remembered_account,
    remember_account,
    remembered_account,
    remove_account_files,
    store_avatar_image,
)
from ..core.accounts import Account

__all__ = ["AccountService"]


def _row(account: Account) -> dict[str, Any]:
    """Hesabın tel üzerindeki görünümü. Karma alanları BURADA YOKTUR."""
    return {
        "kimlik": account.account_id,
        "kullanici_adi": account.username,
        "eposta": account.email,
        "avatar": account.avatar,
        "olusturuldu": account.created_at,
    }


class AccountService:
    """Hesap uçlarının tek yeri. Depo enjekte edilebilir: testte gerçek dosya yok."""

    def __init__(self, store: SqliteAccountStore | None = None) -> None:
        self._store = store or SqliteAccountStore()

    def status(self) -> dict[str, Any]:
        """`hesap.durum`: kimlerin olduğu ve şu an kimin açık olduğu."""
        hesaplar = self._store.list_accounts()
        etkin = remembered_account()
        # Hatırlanan hesap silinmiş olabilir; o zaman açık hesap YOKTUR.
        if etkin and not any(hesap.account_id == etkin for hesap in hesaplar):
            forget_remembered_account()
            etkin = ""
        return {
            "ok": True,
            "hesaplar": [_row(hesap) for hesap in hesaplar],
            "etkin": etkin,
            # İlk açılışta kayıt ekranı gösterilmeli; giriş ekranı boş liste ile
            # kullanıcıyı çıkmaza sokardı.
            "kurulum_gerekli": not hesaplar,
        }

    def register(self, data: object) -> dict[str, Any]:
        """`hesap.kayit`: yeni hesap aç, giriş yap, kurtarma kodunu BİR KEZ ver."""
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz kayıt isteği."}
        ilk_hesap = not self._store.list_accounts()
        try:
            sonuc = self._store.create(
                username=str(data.get("kullanici_adi", "")),
                email=str(data.get("eposta", "")),
                password=str(data.get("parola", "")),
                avatar=str(data.get("avatar", "")),
            )
        except AccountError as error:
            return {"ok": False, "metin": str(error)}
        # İlk hesap, hesapsız kurulumun ayarlarını devralır: kullanıcı giriş
        # yaptığında sağlayıcı oturumlarını ve MCP bağlantılarını kaybetmemeli.
        devralinan = adopt_legacy_config(sonuc.account.account_id) if ilk_hesap else ()
        self._activate(sonuc.account.account_id)
        return {
            "ok": True,
            "hesap": _row(sonuc.account),
            "kurtarma_kodu": sonuc.recovery_code,
            "devralinan_ayarlar": list(devralinan),
        }

    def login(self, data: object) -> dict[str, Any]:
        """`hesap.giris`: kullanıcı adı ya da e-posta + parola."""
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz giriş isteği."}
        hesap = self._store.authenticate(
            identifier=str(data.get("kimlik", "")), password=str(data.get("parola", ""))
        )
        if hesap is None:
            # Hangisinin yanlış olduğu SÖYLENMEZ: var olan kullanıcı adlarını
            # deneme yanılmayla bulmayı kolaylaştırırdı.
            return {"ok": False, "metin": "Kullanıcı adı, e-posta veya parola hatalı."}
        self._activate(hesap.account_id)
        return {"ok": True, "hesap": _row(hesap)}

    def logout(self) -> dict[str, Any]:
        """`hesap.cikis`: hatırlanan seçimi bırak."""
        clear_active_account()
        forget_remembered_account()
        return {"ok": True}

    def recover(self, data: object) -> dict[str, Any]:
        """`hesap.kurtar`: kurtarma koduyla yeni parola belirle."""
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz kurtarma isteği."}
        try:
            degisti = self._store.reset_password(
                identifier=str(data.get("kimlik", "")),
                recovery_code=str(data.get("kurtarma_kodu", "")),
                new_password=str(data.get("yeni_parola", "")),
            )
        except AccountError as error:
            return {"ok": False, "metin": str(error)}
        if not degisti:
            return {"ok": False, "metin": "Kurtarma kodu bu hesapla eşleşmiyor."}
        return {"ok": True}

    def update(self, data: object) -> dict[str, Any]:
        """`hesap.guncelle`: kullanıcı adı, e-posta ve avatar."""
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz güncelleme isteği."}
        try:
            hesap = self._store.update_profile(
                str(data.get("kimlik", "")),
                username=str(data.get("kullanici_adi", "")),
                email=str(data.get("eposta", "")),
                avatar=str(data.get("avatar", "")),
            )
        except AccountError as error:
            return {"ok": False, "metin": str(error)}
        return {"ok": True, "hesap": _row(hesap)}

    def upload_avatar(self, data: object) -> dict[str, Any]:
        """`hesap.avatar_yukle`: seçilen görseli hesabın dizinine kopyala.

        Kopya YAPILIR, kaynağa bağlı kalınmaz: kullanıcı dosyayı taşıdığında ya
        da harici diski çıkardığında avatarın kaybolması kabul edilemez.
        """
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz avatar isteği."}
        kimlik = str(data.get("kimlik", "")).strip()
        if not kimlik:
            return {"ok": False, "metin": "Hesap belirtilmedi."}
        try:
            yol = store_avatar_image(kimlik, str(data.get("yol", "")))
        except (ValueError, OSError) as error:
            return {"ok": False, "metin": str(error)}
        return {"ok": True, "avatar": yol}

    def remove(self, data: object) -> dict[str, Any]:
        """`hesap.sil`: hesabı ve ona ait ayarları kaldır.

        Onay ARAYÜZDE alınır; buraya gelen istek kararın verilmiş olduğu
        anlamına gelir. Silme geri alınamaz ve ürünün açık sözü budur.
        """
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz silme isteği."}
        kimlik = str(data.get("kimlik", "")).strip()
        if not self._store.delete(kimlik):
            return {"ok": False, "metin": "Hesap bulunamadı."}
        remove_account_files(kimlik)
        if remembered_account() == kimlik:
            self.logout()
        return {"ok": True}

    def _activate(self, account_id: str) -> None:
        """Hesabı bu süreçte aç ve "beni hatırla" işaretçisini yaz."""
        activate_account(account_id)
        remember_account(account_id)
