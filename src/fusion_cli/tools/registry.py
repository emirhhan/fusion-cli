"""Araç kayıt defteri.

Yeni bir araç eklemek buraya bir kayıt eklemekten ibarettir; motor kodu değişmez.
Takma adlar (alias) aynı executor'ı ikinci bir adla açar — bazı modeller `read_file`
yerine `view_file` çağırmayı tercih eder ve bu bir hataya dönüşmemelidir.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Iterator

from ..core.errors import FusionError
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .args import ArgumentError


class ToolRegistry:
    """Ada göre araç tutan, şema listesi üretebilen kayıt defteri."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise FusionError(f"Araç adı zaten kayıtlı: {tool.name}")
        self._tools[tool.name] = tool

    def register_alias(self, alias: str, target: str) -> None:
        """Var olan bir aracı ikinci bir adla da aç (aynı executor, aynı şema)."""
        tool = self.get(target)
        if tool is None:
            raise FusionError(f"Takma ad kurulamadı, hedef araç yok: {target}")
        self.register(
            Tool(
                name=alias,
                description=tool.description,
                parameters=tool.parameters,
                run=tool.run,
                mutating=tool.mutating,
            )
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self, allowed: Iterable[str] | None = None) -> list[dict[str, object]]:
        """Modele verilecek şemalar. `allowed` verilirse yalnızca o araçlar döner."""
        if allowed is None:
            return [tool.schema() for tool in self._tools.values()]
        permitted = set(allowed)
        return [tool.schema() for name, tool in self._tools.items() if name in permitted]

    async def execute(self, name: str, args: ToolArgs, context: ToolContext) -> ToolResult:
        """Bir aracı çalıştır ve HER durumda `ToolResult` döndür.

        İstisnaların sonuca çevrildiği TEK yer burasıdır: executor'lar kendi
        try/except kalabalığını taşımaz, motor da araç çağrısı yüzünden çökmez.
        Model hatayı okur ve düzeltilmiş bir çağrı yapabilir.

        Senkron ve asenkron executor'lar aynı şekilde çalıştırılır.
        """
        tool = self.get(name)
        if tool is None:
            return ToolResult.failure(
                f"Bilinmeyen araç: {name}. Kullanılabilir araçlar: {', '.join(self.names())}"
            )
        try:
            outcome = tool.run(args, context)
            return await outcome if inspect.isawaitable(outcome) else outcome
        except ArgumentError as exc:
            return ToolResult.failure(str(exc))
        # Geniş yakalama bilinçli: burası araç sınırıdır. Beklenmedik bir hata turu
        # düşürmez; modele okunabilir biçimde iletilir ve düzeltme şansı doğar.
        except Exception as exc:
            return ToolResult.failure(
                f"Araç çalışırken beklenmedik hata ({name}): {type(exc).__name__}: {exc}"
            )

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
