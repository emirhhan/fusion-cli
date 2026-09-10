"""Sağlayıcı oturumu üzerinden çalışan MCP köprüsü (vekil taşıma).

Fusion'ın ajanı `MetaAds__get_campaigns(...)` gibi TİPLİ bir araç görür. Altında
her çağrı üç adıma iner: Fusion argümanları kurar → sağlayıcının web oturumuna
katı bir talimat yazılır → modelin KENDİ MCP çağrısı gerçek işi yapar ve ham JSON
geri gelir. Yani web sağlayıcı bir MCP TAŞIYICISIDIR; Fusion sunucuyla hiç
konuşmaz.

Neden bu yol var — ölçülmüş engel: Meta'nın barındırdığı MCP dinamik istemci
kaydını reddediyor ve başkalarının reklam hesabına OAuth ile girmek App Review
istiyor. Aynı sunucu ChatGPT/Claude/Gemini'nin connector ekranından tek girişle
bağlanıyor, çünkü o istemciler sunucu tarafında onaylı.

SINIRLAYICI NEDEN DÜZ METİN — `core/tool_emulation` içindeki ölçülmüş ders aynen
geçerlidir: `<tool_call>` gibi HTML'e benzeyen işaretler, HTML render eden bir
kanalda sıkı temizleyici tarafından ÇOCUKLARIYLA birlikte siliniyor ve mesaj
boşalıyordu. Bu tuzak DÖNÜŞ yolunda da vardır, bu yüzden sonuç zarfı kendi
satırlarında duran düz büyük harfli işaretlerdir.

Bu modül tarayıcı BİLMEZ: kanal `ask` ile enjekte edilir. Böylece sözleşme ve
hata davranışı gerçek Chrome açmadan test edilebilir (aynı gerekçe
`providers/web_shared_browser.py` için de geçerliydi).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ..config.models import HostedConnectorConfig
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ..tools import ToolRegistry

__all__ = [
    "RESULT_CLOSE",
    "RESULT_OPEN",
    "HostedConnectorClient",
    "HostedRelayError",
    "HostedTool",
    "parse_result",
]

_LOG = logging.getLogger(__name__)

#: Sonuç zarfı. Kendi satırlarında duran düz işaretler; ne HTML ne Markdown
#: anlamı taşır, bu yüzden render edilirken dönüşüme uğramazlar.
RESULT_OPEN = "FUSION_MCP_RESULT"
RESULT_CLOSE = "FUSION_MCP_RESULT_END"

_BLOCK = re.compile(
    rf"{re.escape(RESULT_OPEN)}\s*(?P<body>.*?)\s*{re.escape(RESULT_CLOSE)}",
    re.DOTALL,
)
#: Model JSON'u kod bloğuna almaya bayılır; bu içeriği bozmamalı.
_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n(?P<body>.*?)\n?```$", re.DOTALL)

#: Kanal: (connector, istem) → modelin metin cevabı.
AskSession = Callable[[HostedConnectorConfig, str], Awaitable[str]]

MESSAGE_NO_ENVELOPE = (
    f"sağlayıcı cevabında {RESULT_OPEN} zarfı yok; sonuç okunamadı "
    "(model işi yapmış olabilir ama doğrulanamaz)"
)


class HostedRelayError(RuntimeError):
    """Sağlayıcı cevabı sözleşmeye uymadı."""


@dataclass(frozen=True, slots=True)
class HostedTool:
    """Sağlayıcı connector'ından keşfedilmiş araç tanımı."""

    connector: str
    name: str
    description: str = ""
    schema: Mapping[str, object] = field(default_factory=dict)


def parse_result(text: str) -> object:
    """Zarfı bul, gövdeyi JSON olarak çöz.

    Zarf yoksa HATA verilir. Düz metni "başarı" saymak, modelin özet geçtiği her
    turda Fusion'ın işin yapıldığını sanmasına yol açardı — `mcp_bridge/client.py`
    aynı sınıftan bir hatayı (`isError` bayrağının atılması) zaten bir kez ödedi.
    """
    match = _BLOCK.search(text)
    if match is None:
        raise HostedRelayError(MESSAGE_NO_ENVELOPE)
    body = match.group("body").strip()
    fenced = _FENCE.match(body)
    if fenced is not None:
        body = fenced.group("body").strip()
    if not body:
        raise HostedRelayError(f"{RESULT_OPEN} zarfı boş geldi")
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError) as error:
        raise HostedRelayError(f"zarf içeriği JSON değil: {error}") from error


def _envelope_rules() -> str:
    return (
        f"Cevabını ŞU BİÇİMDE ver ve başka hiçbir şey ekleme:\n"
        f"{RESULT_OPEN}\n<tek bir JSON nesnesi>\n{RESULT_CLOSE}\n"
        "Özetleme, yorum yazma, sonucu kendi cümlelerinle anlatma."
    )


def render_discovery_prompt(connector: HostedConnectorConfig) -> str:
    """Connector'ın araçlarını ve JSON şemalarını isteyen istem."""
    return (
        f"Bağlı connector: {connector.name} ({connector.url}).\n"
        "Bu connector'ın SANA sunduğu araçları listele. Her araç için adını, kısa "
        "açıklamasını ve girdi JSON şemasını ver.\n"
        '{"araclar": [{"ad": "...", "aciklama": "...", "sema": {...}}]}\n'
        f"{_envelope_rules()}"
    )


def render_call_prompt(
    connector: HostedConnectorConfig, tool: str, args: Mapping[str, object]
) -> str:
    """Aracı TAM BU argümanlarla çağırmasını isteyen istem."""
    return (
        f"Bağlı connector: {connector.name} ({connector.url}).\n"
        f"'{tool}' aracını TAM OLARAK şu argümanlarla çağır; argümanları "
        "değiştirme, ekleme, çıkarma:\n"
        f"{json.dumps(args, ensure_ascii=False, indent=2)}\n"
        "Aracın döndürdüğü sonucu HAM hâliyle aktar:\n"
        '{"ok": true, "sonuc": <aracın döndürdüğü değer>}\n'
        'Araç hata verirse: {"ok": false, "hata": "<aracın verdiği hata metni>"}\n'
        f"{_envelope_rules()}"
    )


def _repair_reminder() -> str:
    return (
        "Önceki cevabında zarf yoktu, bu yüzden sonuç okunamadı. Aracı TEKRAR "
        f"çağırmana gerek yok; son sonucu yalnızca {RESULT_OPEN} / {RESULT_CLOSE} "
        "arasında tek bir JSON nesnesi olarak yaz. Açıklama ekleme."
    )


class HostedConnectorClient:
    """Sağlayıcı-barındırmalı connector'ları `McpClient` sözleşmesiyle sunar.

    `list_tools` / `call` / `register_into` imzaları kasıtlı olarak `McpClient` ile
    aynıdır: Fusion'ın ajanı iki taşıma arasındaki farkı görmez.
    """

    def __init__(self, connectors: Sequence[HostedConnectorConfig], *, ask: AskSession) -> None:
        self._connectors = {connector.name: connector for connector in connectors}
        self._ask = ask

    def _connector(self, name: str) -> HostedConnectorConfig:
        connector = self._connectors.get(name)
        if connector is None:
            raise HostedRelayError(f"Bağlantı tanımlı değil: {name}")
        return connector

    async def list_tools(self, connector: str) -> list[HostedTool]:
        """Connector'ın araçlarını sağlayıcı oturumuna sorarak keşfet."""
        config = self._connector(connector)
        payload = await self._exchange(config, render_discovery_prompt(config))
        if not isinstance(payload, Mapping):
            raise HostedRelayError("keşif cevabı JSON nesnesi değil")
        raw = payload.get("araclar")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise HostedRelayError("keşif cevabında 'araclar' listesi yok")
        tools: list[HostedTool] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("ad", "")).strip()
            if not name:
                continue
            schema = item.get("sema")
            tools.append(
                HostedTool(
                    connector=connector,
                    name=name,
                    description=str(item.get("aciklama", "")),
                    schema=dict(schema) if isinstance(schema, Mapping) else {},
                )
            )
        return tools

    async def call(self, connector: str, tool: str, args: Mapping[str, object]) -> ToolResult:
        """Aracı sağlayıcı oturumu üzerinden çağır ve sonucu kanonik hâle getir."""
        config = self._connector(connector)
        try:
            payload = await self._exchange(config, render_call_prompt(config, tool, args))
        except HostedRelayError as error:
            # Görünür hata: modele düzeltme şansı verir, sessizce başarı saymaz.
            return ToolResult.failure(f"{connector}.{tool} sonucu okunamadı: {error}")
        if not isinstance(payload, Mapping):
            return ToolResult.failure(f"{connector}.{tool}: cevap JSON nesnesi değil")
        if payload.get("ok") is False:
            hata = str(payload.get("hata", "")) or "uzak araç hata verdi"
            # Hata METNİ olduğu gibi taşınır: uzak sunucular çözüm önerisini
            # genelde oraya yazar (bkz. `mcp_bridge/client.py`).
            return ToolResult.failure(f"{connector}.{tool} başarısız: {hata}")
        sonuc = payload.get("sonuc", payload)
        structured = sonuc if isinstance(sonuc, Mapping) else {"sonuc": sonuc}
        return ToolResult(output=json.dumps(sonuc, ensure_ascii=False), structured=dict(structured))

    async def _exchange(self, connector: HostedConnectorConfig, prompt: str) -> object:
        """İstemi gönder, zarfı çöz; bozuksa BİR kez katı hatırlatmayla tekrar sor."""
        answer = await self._ask(connector, prompt)
        try:
            return parse_result(answer)
        except HostedRelayError as first:
            _LOG.info(
                "sağlayıcı cevabı sözleşmeye uymadı, onarım isteniyor",
                extra={"baglanti": connector.name, "hata": str(first)},
            )
        repaired = await self._ask(connector, _repair_reminder())
        return parse_result(repaired)

    async def register_into(self, registry: ToolRegistry) -> tuple[str, ...]:
        """Doğrulanmış connector'ların araçlarını kayıt defterine ekle.

        Doğrulanmamış connector için oturuma HİÇ gidilmez: ölçülmemiş bir
        connector'ın araçlarını kaydetmek, modelin var olmayan yeteneklere
        güvenmesine yol açar (`WebSessionConfig.tool_eval_passed` ile aynı gerekçe).
        """
        added: list[str] = []
        for name, connector in self._connectors.items():
            if not connector.verified:
                continue
            try:
                tools = await self.list_tools(name)
            except HostedRelayError as error:
                _LOG.warning(
                    "connector araçları keşfedilemedi",
                    extra={"baglanti": name, "hata": str(error)},
                )
                continue
            for tool in tools:
                fusion_name = f"{name}__{tool.name}"
                registry.register_or_replace(
                    Tool(
                        name=fusion_name,
                        description=tool.description,
                        parameters=dict(tool.schema),
                        run=self._make_run(name, tool.name),
                        # Dış aracın ne yaptığı bilinemez: onay akışına girsin.
                        mutating=True,
                    )
                )
                added.append(fusion_name)
        return tuple(added)

    def _make_run(
        self, connector: str, tool: str
    ) -> Callable[[ToolArgs, ToolContext], Awaitable[ToolResult]]:
        async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
            del context
            try:
                return await self.call(connector, tool, dict(args))
            except Exception as error:
                return ToolResult.failure(f"Bağlantı aracı hatası ({connector}.{tool}): {error}")

        return _run
