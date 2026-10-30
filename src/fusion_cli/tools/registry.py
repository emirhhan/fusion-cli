"""Araç kayıt defteri.

Yeni bir araç eklemek buraya bir kayıt eklemekten ibarettir; motor kodu değişmez.
Takma adlar (alias) aynı executor'ı ikinci bir adla açar — bazı modeller `read_file`
yerine `view_file` çağırmayı tercih eder ve bu bir hataya dönüşmemelidir.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Iterable, Iterator
from dataclasses import replace
from threading import Event

from ..core.artifacts import offload_output
from ..core.constants import MAX_OUTPUT_CHARS
from ..core.errors import CleanupFailedError, FusionError, PathAccessError
from ..core.owned_thread import await_cancellable_thread
from ..core.tools import Tool, ToolArgs, ToolContext, ToolExecutor, ToolResult
from .arg_aliases import adapt_arguments, normalize_name
from .args import ArgumentError
from .injection import flag_injection

#: `_CancellationEvent.wait` üst olayı bu aralıkla yoklar.
_WAIT_SLICE_S = 0.05


class _CancellationEvent(Event):
    """Çağrının iptalini parent iptal sinyaliyle birlikte gözle."""

    def __init__(self, parent: Event) -> None:
        super().__init__()
        self._parent = parent

    def is_set(self) -> bool:
        return super().is_set() or self._parent.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """`threading.Event.wait` kendi iç bayrağına bakar; üst iptali de gözle.

        Ölçüldü (30 Ekim): `cancelled.wait(5)` ile uyuyan araç, üst iptal gelse bile
        süre dolana kadar uyanmıyordu (yalnız `is_set()` geçersiz kılınmıştı).
        """
        bitis = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            kalan = _WAIT_SLICE_S if bitis is None else min(_WAIT_SLICE_S, bitis - time.monotonic())
            if kalan <= 0:
                return False
            super().wait(kalan)
        return True


def _run_sync(run: ToolExecutor, args: ToolArgs, context: ToolContext) -> ToolResult:
    """Senkron executor'ı thread içinde çağırıp `ToolResult` döndür.

    Yalnızca `iscoroutinefunction` False olan executor'lar buraya gelir; dönüş
    her zaman `ToolResult`'tur (Awaitable değil).
    """
    if context.cancelled.is_set():
        return ToolResult.failure("Araç başlamadan iptal edildi.")
    result = run(args, context)
    assert isinstance(result, ToolResult)  # senkron yol: Awaitable dönmez
    return result


class ToolRegistry:
    """Ada göre araç tutan, şema listesi üretebilen kayıt defteri."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise FusionError(f"Araç adı zaten kayıtlı: {tool.name}")
        self._tools[tool.name] = tool

    def register_or_replace(self, tool: Tool) -> None:
        """Aynı adı taşıyan aracı ÜZERİNE YAZ — yalnız dış (uzak) araçlar için.

        Yerel araçlarda yinelenen ad bir programlama hatasıdır ve `register`
        haklı olarak hata verir. Uzak araçlar ise her keşifte yeniden gelir ve
        şemaları sunucu tarafında değişebilir: MCP bağlantısı artık oturum boyunca
        yaşadığı için aynı kayıt defteri ikinci turda yeniden beslenebilir
        (bkz. `mcp_bridge/pool.py`). Orada doğru davranış hata vermek değil, taze
        şemayı geçirmektir.
        """
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
                advertised=False,
            )
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def resolve(self, name: str) -> Tool | None:
        """Ada göre ara; bulunamazsa büyük/küçük harf, tire ve CamelCase farkını yok say."""
        tool = self._tools.get(name)
        if tool is not None:
            return tool
        wanted = normalize_name(name)
        for candidate_name, candidate in self._tools.items():
            if normalize_name(candidate_name) == wanted:
                return candidate
        return None

    def advertised_names(self) -> tuple[str, ...]:
        """Modele sunulan (gizli takma ad olmayan) araç adları."""
        return tuple(name for name, tool in self._tools.items() if tool.advertised)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self, allowed: Iterable[str] | None = None) -> list[dict[str, object]]:
        """Modele verilecek şemalar. `allowed` verilirse yalnızca o araçlar döner."""
        if allowed is None:
            return [tool.schema() for tool in self._tools.values() if tool.advertised]
        permitted = set(allowed)
        return [
            tool.schema()
            for name, tool in self._tools.items()
            if name in permitted and tool.advertised
        ]

    async def execute(self, name: str, args: ToolArgs, context: ToolContext) -> ToolResult:
        """Bir aracı çalıştır ve HER durumda `ToolResult` döndür.

        İstisnaların sonuca çevrildiği TEK yer burasıdır: executor'lar kendi
        try/except kalabalığını taşımaz, motor da araç çağrısı yüzünden çökmez.
        Model hatayı okur ve düzeltilmiş bir çağrı yapabilir.

        Senkron ve asenkron executor'lar aynı şekilde çalıştırılır. Senkron
        executor'lar (shell, dosya I/O, ChromaDB sorgusu gibi bloklayan işler)
        `asyncio.to_thread` ile ayrı bir iş parçacığında çalıştırılır: event
        loop bloklanmaz, arka plan işleri (ders çıkarımı, model ısıtma) stall olmaz.
        """
        tool = self.resolve(name)
        if tool is None:
            # Yalnız SUNULAN adlar: gizli takma adları dökmek bağlamı şişirir ve modele
            # gizli adları öğretir (ölçüldü, 30 Ekim).
            return ToolResult.failure(
                f"Bilinmeyen araç: {name}. Kullanılabilir araçlar: "
                f"{', '.join(self.advertised_names())}"
            )
        args = adapt_arguments(tool, args)
        try:
            if _is_async(tool.run):
                outcome = tool.run(args, context)
                return _finish(await outcome, name, context)  # coroutine ToolResult döndürür
            # Senkron executor: bloklamaması için thread'e alınır.
            # İptal belirteci çağrıya özeldir. Oturum bağlamındaki aynı Event'i
            # kullanmak, iptal edilen bir aramadan sonraki bütün araçları zehirler;
            # `replace` diğer paylaşılan değişiklik/todo/tarayıcı durumunu korur.
            invocation_context = replace(context, cancelled=_CancellationEvent(context.cancelled))
            sonuc = await await_cancellable_thread(
                _run_sync, invocation_context.cancelled.set, tool.run, args, invocation_context
            )
            return _finish(sonuc, name, context)
        except CleanupFailedError:
            raise
        except (ArgumentError, PathAccessError) as exc:
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


def _is_async(run: ToolExecutor) -> bool:
    """`async def` işlevi ya da `async def __call__` taşıyan nesne mi?"""
    return inspect.iscoroutinefunction(run) or inspect.iscoroutinefunction(
        getattr(run, "__call__", None)  # noqa: B004 - çağrılabilir nesnenin yöntemi aranıyor
    )


def _finish(result: ToolResult, name: str, context: ToolContext) -> ToolResult:
    """Araç sonucunu modele gitmeye hazırla: diske al, enjeksiyon notunu ekle.

    Not her araç için eklenir: dosya, web sayfası, komut çıktısı ve uzak araç
    yanıtı aynı güvensiz veridir. Tarama TAM çıktı üzerinde, not ise diske alma
    SONRASINDA yapılır — kısaltılan önizlemede de görünsün diye.
    """
    return flag_injection(_offload(result, name, context), result.output)


def _offload(result: ToolResult, name: str, context: ToolContext) -> ToolResult:
    """Bağlamı şişiren çıktıyı artifact'a al.

    TEK yerde yapılır: her aracın kendi kırpma kuralını yazması, aynı hatayı her
    araçta yeniden üretmek demekti. Depo yoksa davranış aynen korunur.
    """
    if context.artifacts is None or not result.output:
        return result
    output, path = offload_output(
        result.output, store=context.artifacts, tool=name, limit=MAX_OUTPUT_CHARS
    )
    if path is None:
        return result
    return replace(result, output=output, artifact_path=str(path))
