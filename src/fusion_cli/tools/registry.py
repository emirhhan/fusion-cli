"""Araç kayıt defteri.

Yeni bir araç eklemek buraya bir kayıt eklemekten ibarettir; motor kodu değişmez.
Takma adlar (alias) aynı executor'ı ikinci bir adla açar — bazı modeller `read_file`
yerine `view_file` çağırmayı tercih eder ve bu bir hataya dönüşmemelidir.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable, Iterable, Iterator
from dataclasses import replace
from threading import Event
from typing import Literal, cast

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
_EDIT_PREFERENCE_NOTE = (
    "Bu turun önerilen düzenleme biçimi bu araçtır; açık kullanıcı seçimi, "
    "izinler, tam okuma ve güncellik/yapı kontrolleri önceliklidir."
)


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
        #: `register_or_replace` ile gelen (uzak/eklenti) araç adları; sıkı yüzeyde sayılır.
        self._remote: set[str] = set()
        # Runtime-owned admission is deliberately not copied with tool objects.
        # Search state can be shared; authority cannot be shared across clones.
        self._tool_search_permitted: Callable[[], set[str]] | None = None

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
        self._remote.add(tool.name)

    def unregister_remote(self, name: str) -> bool:
        """Uzak aracı defterden çıkar (MCP `tools/list_changed` ile kalkan araç); yerel araca
        dokunulmaz."""
        if name not in self._remote:
            return False
        self._remote.discard(name)
        self._tools.pop(name, None)
        return True

    def is_remote(self, name: str) -> bool:
        """Araç uzak (MCP/eklenti) kaynaklı mı — `register_or_replace` ile mi geldi?"""
        return name in self._remote

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
                evidence_role=tool.evidence_role,
                evidence_role_resolver=tool.evidence_role_resolver,
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

    def schemas(
        self,
        allowed: Iterable[str] | None = None,
        *,
        edit_format: Literal["exact", "whole"] | None = None,
    ) -> list[dict[str, object]]:
        """Yalnız izinli şemaları ver; tavsiye araç yetkisini değiştirmez."""
        if edit_format not in {None, "exact", "whole"}:
            raise ValueError("Geçersiz düzenleme biçimi tavsiyesi.")
        permitted = None if allowed is None else set(allowed)
        preferred = {"exact": "edit_file", "whole": "write_file"}.get(edit_format or "")
        schemas = []
        for name, tool in self._tools.items():
            if not tool.advertised or (permitted is not None and name not in permitted):
                continue
            if name == preferred:
                tool = replace(
                    tool,
                    description=tool.description + " " + _EDIT_PREFERENCE_NOTE,
                )
            schemas.append(tool.schema())
        return schemas

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
        return await self.execute_registered(tool, args, context)

    async def execute_registered(
        self, tool: Tool, args: ToolArgs, context: ToolContext
    ) -> ToolResult:
        """Dispatch the exact already-admitted immutable tool, without another lookup."""
        name = tool.name
        args = adapt_arguments(tool, args)
        try:
            if _is_async(tool.run):
                outcome = cast("Awaitable[ToolResult]", tool.run(args, context))
                return _finish(await outcome, tool, context)  # coroutine ToolResult döndürür
            # Senkron executor: bloklamaması için thread'e alınır.
            # İptal belirteci çağrıya özeldir. Oturum bağlamındaki aynı Event'i
            # kullanmak, iptal edilen bir aramadan sonraki bütün araçları zehirler;
            # `replace` diğer paylaşılan değişiklik/todo/tarayıcı durumunu korur.
            invocation_context = replace(context, cancelled=_CancellationEvent(context.cancelled))
            sonuc = await await_cancellable_thread(
                _run_sync, invocation_context.cancelled.set, tool.run, args, invocation_context
            )
            return _finish(sonuc, tool, context)
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


def _finish(result: ToolResult, tool: Tool, context: ToolContext) -> ToolResult:
    """Araç sonucunu modele gitmeye hazırla: diske al, enjeksiyon notunu ekle.

    Not her araç için eklenir: dosya, web sayfası, komut çıktısı ve uzak araç
    yanıtı aynı güvensiz veridir. Tarama TAM çıktı üzerinde, not ise diske alma
    SONRASINDA yapılır — kısaltılan önizlemede de görünsün diye. `verbatim_output`
    araçları (beceri gövdesi, #139) bu iki adımın dışındadır.
    """
    if tool.verbatim_output:
        return result
    return flag_injection(_offload(result, tool.name, context), result.output)


def _offload(result: ToolResult, name: str, context: ToolContext) -> ToolResult:
    """Bağlamı şişiren çıktıyı artifact'a al.

    TEK yerde yapılır: her aracın kendi kırpma kuralını yazması, aynı hatayı her
    araçta yeniden üretmek demekti. Depo yoksa davranış aynen korunur.
    """
    if context.artifacts is None or not result.output or result.output_shaped:
        return result
    output, path = offload_output(
        result.output, store=context.artifacts, tool=name, limit=MAX_OUTPUT_CHARS
    )
    if path is None:
        return result
    return replace(
        result,
        output=output,
        artifact_path=str(path),
        source_read_scope="truncated" if result.source_read_url else result.source_read_scope,
    )
