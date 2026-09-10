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
#: Geçmişte tutulan en fazla mesaj: önsöz + son istem + son cevap.
_KEPT_MESSAGES = 3

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
    _histories: dict[tuple[str, str], list[Message]] = field(default_factory=dict, init=False)

    async def __call__(self, connector: HostedConnectorConfig, prompt: str) -> str:
        session = self._session_for(connector)
        key = (connector.provider, connector.account)
        history = self._histories.setdefault(key, [Message(role="user", content=PREAMBLE)])
        history.append(Message(role="user", content=prompt))
        transport = build_browser_transport(
            session, timeout_s=session.timeout_s, trace_dir=self.trace_dir
        )
        turn = await transport(self._credential(session), tuple(history), session.model)
        history.append(Message(role="assistant", content=turn.text))
        self._trim(history)
        return turn.text

    @staticmethod
    def _trim(history: list[Message]) -> None:
        """Önsözü ve yalnız SON alışverişi tut.

        Gönderilmiş önek korunmak zorunda değil: `_deliver_turn` konuşmaya yalnız
        gönderilmemiş kısmı yazar. Sınırsız biriken liste iki maliyet üretiyordu —
        oturum boyunca büyüyen bellek ve her çağrıda tüm geçmişi tarayan
        `_task_reminder`, yani N çağrıda O(N²) iş. Önsöz yerinde KALIR: havuz
        konuşmayı `messages[:1]` ile eşler, onu düşürmek her çağrıda yeni sekme
        açardı.
        """
        if len(history) <= _KEPT_MESSAGES:
            return
        del history[1 : len(history) - (_KEPT_MESSAGES - 1)]

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
