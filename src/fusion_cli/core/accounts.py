"""Yerel hesap tipleri ve depo sözleşmesi.

Fusion'ın hesapları SUNUCUDA DEĞİL, kullanıcının kendi bilgisayarındadır: bir
hesap silindiğinde ya da uygulama kaldırıldığında ona ait her şey kaybolur.
Bu bilinçli bir karardır — kimlik doğrulama bir ağ hizmeti değil, aynı makineyi
paylaşan kişilerin işlerini ayırmasıdır.

`core` saf kalır: burada yalnız tipler ve protokol durur, SQLite ve parola
karması `accounts` katmanındadır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Account:
    """Bir yerel hesabın parolasız görünümü.

    Parola karması ve kurtarma karması BU TİPTE TAŞINMAZ: hesap bilgisi arayüze
    ve RPC yanıtlarına kadar gider, karma ise depodan dışarı çıkmamalıdır.
    """

    account_id: str
    username: str
    email: str
    #: Kısa görsel işaret (emoji). Dosya yolu değil: hesap taşınırken kırılmasın.
    avatar: str = ""
    created_at: float = 0.0


@dataclass(frozen=True, slots=True)
class AccountCreation:
    """Yeni hesap sonucu: hesabın kendisi ve BİR KEZ gösterilen kurtarma kodu."""

    account: Account
    #: Düz metin kurtarma kodu. Yalnız burada döner; depoda yalnız karması var.
    recovery_code: str


class AccountStore(Protocol):
    """Hesap deposunun sözleşmesi.

    Motor ve uygulama katmanı SQLite bilmez; testte sahte depo verilebilir.
    """

    def list_accounts(self) -> tuple[Account, ...]: ...

    def create(
        self, *, username: str, email: str, password: str, avatar: str = ""
    ) -> AccountCreation: ...

    def authenticate(self, *, identifier: str, password: str) -> Account | None: ...

    def reset_password(self, *, identifier: str, recovery_code: str, new_password: str) -> bool: ...

    def update_profile(
        self, account_id: str, *, username: str, email: str, avatar: str
    ) -> Account: ...

    def delete(self, account_id: str) -> bool: ...
