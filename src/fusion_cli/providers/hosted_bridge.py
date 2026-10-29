"""Connector istemlerini ilgili web oturumuna taşıyan kanal.

`mcp_bridge/hosted.py` tarayıcı BİLMEZ: sözleşme ve hata davranışı gerçek Chrome
açmadan test edilebilsin diye kanal enjekte edilir. Bu modül o kanalın gerçek
uygulamasıdır ve iki katmanı birbirine bağlar.

KONUŞMA SÜREKLİ OLMAK ZORUNDA. `BrowserSessionPool` konuşmaları `messages[:1]`
özetiyle eşler; her çağrıda farklı bir ilk mesaj göndermek her araç çağrısı için
YENİ bir sekme açardı. Bu hem yavaştır hem de connector bağlamını kaybeder:
onarım istemi ("önceki cevabında zarf yoktu") ancak aynı konuşmada anlam taşır.
Bu yüzden connector başına sabit bir önsöz mesajıyla başlayan geçmiş tutulur.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..config.models import Config, HostedConnectorConfig, WebSessionConfig
from ..core.types import Message
from ..mcp_bridge.hosted import HostedRelayError
from .web_browser import build_browser_transport
from .web_session import WebSessionCredential

__all__ = ["PREAMBLE", "HostedSessionChannel"]

#: Connector başına konuşmayı açan SABİT mesaj. Sabit olması zorunludur (bkz.
#: modül açıklaması): havuz konuşmayı bu mesajın özetiyle bulur.
#: Geçmişin en çok mesaj sayısı (önsöz + 20 alışveriş). Aşılınca konuşma BİR KEZ
#: sıfırlanır (yeni sohbet); her çağrıda kırpılmaz — gerekçesi `_start_fresh_if_full`.
_MAX_MESSAGES = 41

PREAMBLE = (
    "Bu konuşma Fusion ile kurulmuş otomatik bir köprüdür. Sana bağlı connector "
    "araçlarını çağırmanı isteyeceğim. Her seferinde yalnızca istenen aracı çağır "
    "ve sonucu istenen zarf biçiminde ver; özet geçme, yorum ekleme. Anladıysan "
    "yalnızca hazır olduğunu söyle."
)


@dataclass(slots=True)
class HostedSessionChannel:
    """Connector + istem → modelin metin cevabı."""

    config: Config
    #: Gizli çözümü için şifreli depo (cookie başlığı). Yoksa boş kimlikle gidilir.
    secret_store: object | None = None
    trace_dir: Path | None = None
    #: Sağlayıcının kendi tur süresini AŞAN bir taban. Doğrulama turu için
    #: kullanılır: sağlayıcı başına ayarlanan süre oraya dar geliyordu.
    timeout_floor_s: float | None = None
    _histories: dict[tuple[str, str], list[Message]] = field(default_factory=dict, init=False)

    async def __call__(self, connector: HostedConnectorConfig, prompt: str) -> str:
        session = self._session_for(connector)
        key = (connector.provider, connector.account)
        history = self._histories.setdefault(key, [Message(role="user", content=PREAMBLE)])
        self._start_fresh_if_full(history)
        history.append(Message(role="user", content=prompt))
        timeout_s = session.timeout_s
        if self.timeout_floor_s is not None:
            timeout_s = max(timeout_s, self.timeout_floor_s)
        transport = build_browser_transport(session, timeout_s=timeout_s, trace_dir=self.trace_dir)
        turn = await transport(self._credential(session), tuple(history), session.model)
        history.append(Message(role="assistant", content=turn.text))
        return turn.text

    @staticmethod
    def _start_fresh_if_full(history: list[Message]) -> None:
        """Geçmiş tavana ulaştıysa konuşmayı önsöze indir (yeni sohbet, bir kez).

        Gönderilmiş önek DEĞİŞMEMELİ: `_deliver_turn` sohbeti yalnız `messages[:sent_count]`
        özeti birebir eşleşirse sürdürür. Eskiden her çağrıda ortadan kırpılıyordu; 3.
        çağrıdan itibaren önek uyuşmuyor, her connector çağrısı yeni sohbet/sekme açıp
        hız sınırı bekliyordu (P1-02). Bellek ve `_task_reminder` taraması tavanla
        sınırlı kalır; önsöz yerinde durur (havuz konuşmayı `messages[:1]` ile eşler).
        """
        if len(history) >= _MAX_MESSAGES:
            del history[1:]

    def _session_for(self, connector: HostedConnectorConfig) -> WebSessionConfig:
        """Connector'ı taşıyacak oturumu bul; yoksa SEBEBİ söyleyerek düş.

        Sessizce boş cevap dönmek, kullanıcının aracın çalıştığını sanmasına yol
        açardı. Aynı olgu arayüzde `hosted_connector_ready()` ile uyarı olarak da
        gösterilir.
        """
        for session in self.config.web_sessions:
            if (
                session.provider == connector.provider
                and session.account == connector.account
                and session.transport == "browser"
                and session.enabled
                and session.login_verified
            ):
                return session
        raise HostedRelayError(
            f"'{connector.name}' bağlantısı {connector.provider} oturumu üzerinden çalışır, "
            "ama o oturum bağlı değil. Önce ilgili web sağlayıcısına giriş yap."
        )

    def _credential(self, session: WebSessionConfig) -> WebSessionCredential:
        store = self.secret_store
        cookie = ""
        if session.credential_ref and store is not None and getattr(store, "available", False):
            get = getattr(store, "get", None)
            if callable(get):
                cookie = get(session.credential_ref) or ""
        return WebSessionCredential(token=cookie)

    def forget(self, connector: HostedConnectorConfig) -> None:
        """Konuşmayı bırak — oturum düştüyse temiz bir konuşmayla başlanmalı."""
        self._histories.pop((connector.provider, connector.account), None)

    @property
    def conversations(self) -> Mapping[tuple[str, str], int]:
        """Teşhis: connector başına biriken mesaj sayısı."""
        return {key: len(value) for key, value in self._histories.items()}
