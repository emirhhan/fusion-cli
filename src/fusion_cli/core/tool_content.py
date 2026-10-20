"""Araç sonuçlarındaki metin dışı içeriğin kanonik temsili."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolContentType(Enum):
    """Fusion araç sınırında desteklenen içerik türleri."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    RESOURCE_LINK = "resource_link"
    RESOURCE_TEXT = "resource_text"
    RESOURCE_BLOB = "resource_blob"


@dataclass(frozen=True, slots=True)
class ToolContent:
    """Bir araç sonucundaki tek içerik bloğu.

    Büyük ikili veriler modele düz metin olarak verilmez. ``data`` alanı yalnızca
    sağlayıcı sınırında native parçaya çevrilir; ``text`` ise modelin okuyabileceği
    güvenli açıklama veya metin kaynağıdır.
    """

    type: ToolContentType
    text: str = ""
    mime_type: str = ""
    data: str = ""
    uri: str = ""
    name: str = ""
    title: str = ""
    description: str = ""
    size: int | None = None

    @classmethod
    def text_block(cls, text: str) -> ToolContent:
        """Düz metin bloğu üret."""
        return cls(type=ToolContentType.TEXT, text=text)

    @classmethod
    def image(cls, mime_type: str, data: str) -> ToolContent:
        """Base64 kodlu görsel bloğu üret."""
        return cls(type=ToolContentType.IMAGE, mime_type=mime_type, data=data)

    @classmethod
    def audio(cls, mime_type: str, data: str) -> ToolContent:
        """Base64 kodlu ses bloğu üret."""
        return cls(type=ToolContentType.AUDIO, mime_type=mime_type, data=data)

    @classmethod
    def resource_link(
        cls,
        *,
        uri: str,
        name: str,
        title: str = "",
        description: str = "",
        mime_type: str = "",
        size: int | None = None,
    ) -> ToolContent:
        """Dış kaynak bağlantısı bloğu üret."""
        return cls(
            type=ToolContentType.RESOURCE_LINK,
            uri=uri,
            name=name,
            title=title,
            description=description,
            mime_type=mime_type,
            size=size,
        )

    @classmethod
    def resource_text(cls, *, uri: str, text: str, mime_type: str = "") -> ToolContent:
        """Gömülü metin kaynağı bloğu üret."""
        return cls(
            type=ToolContentType.RESOURCE_TEXT,
            uri=uri,
            text=text,
            mime_type=mime_type,
        )

    @classmethod
    def resource_blob(cls, *, uri: str, data: str, mime_type: str = "") -> ToolContent:
        """Gömülü ikili kaynak bloğu üret."""
        return cls(
            type=ToolContentType.RESOURCE_BLOB,
            uri=uri,
            data=data,
            mime_type=mime_type,
        )

    @property
    def data_uri(self) -> str:
        """Görsel/ses verisini sağlayıcının kabul ettiği data URI biçimine çevir."""
        if not self.data or not self.mime_type:
            return ""
        return f"data:{self.mime_type};base64,{self.data}"
