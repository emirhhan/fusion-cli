"""Modele göre araç YÜZEYİ: küçük/zayıf modele sıkı, geniş modele tam liste (T1-63, M1-12).

Ölçüldü (30 Ekim): yerleşik 41+ şema (masaüstü 11, Chrome 5, Playwright 10, arka plan
masaüstü 4…) neredeyse tek istekte gidiyordu ve MCP araçları ayrıca ekleniyordu. Küçük
bağlamlı ya da güvenle araç çağıramayan modelde bu hem bağlamı yer hem araç seçimini
bozar (bkz. `defaults.yaml` `compact_tools_window_tokens`).

Sıkı yüzey (`compact_tool_surface`) üç durumda açılır:

1. `ModelSpec` etiketlerinde açıkça `compact` varsa,
2. bilinen girdi penceresi `runtime.compact_tools_window_tokens` değerini aşmıyorsa,
3. model dosya değiştiren agent olamıyorsa (doğrulanmamış taklit araç): eylem
   yapamayan modele masaüstü/Chrome eylem araçlarını sunmanın anlamı yoktur.

Sıkı yüzeyde:

- `desktop_*` ve `chrome_*` ailesi gizlenir; İSTEK masaüstü işiyse (`masaustu` türü) ya da
  araç `allowed_tools` ile açıkça istenmişse gizlenmez — yoksa kullanıcının doğrudan
  istediği işte "araç yok" derdi.
- MCP/eklenti araçları `runtime.compact_external_tools` ile sınırlanır (kayıt sırasıyla ilk N).

Karar tur başında verilir (`policy_for`) ve `ExecutionPolicy`'de taşınır.
"""

from __future__ import annotations

from collections.abc import Collection

from ...config.models import Config
from ...core.types import ModelSpec
from ...tools.registry import ToolRegistry

#: `ModelSpec.tags` içinde sıkı yüzeyi zorlayan etiket.
COMPACT_TAG = "compact"

#: Sıkı yüzeyde gizlenen araç ad önekleri (masaüstü ve Chrome ailesi).
COMPACT_HIDDEN_PREFIXES = ("desktop_", "chrome_")

#: Sıkı yüzeyde gizliliği kaldıran istek türü (`loop.run_agent` `task_kinds`).
DESKTOP_TASK_KIND = "masaustu"


def is_weak_model(config: Config, spec: ModelSpec, window_tokens: int | None) -> bool:
    """Küçük/zayıf model mi? `compact` etiketi ya da bilinen pencere eşiği aşmıyor.

    Hem sıkı araç yüzeyi hem zayıf modelde erken sıkıştırma (`context_budget`) bu
    TEK tanımı kullanır. Pencere, çağıran tarafından verilir: `context_budget` bu
    modülü de çağırdığı için burada yeniden hesaplanamaz (döngüsel bağımlılık).
    """
    if any(tag.strip().lower() == COMPACT_TAG for tag in spec.tags):
        return True
    threshold = config.runtime.compact_tools_window_tokens
    if threshold <= 0:
        return False
    return window_tokens is not None and window_tokens <= threshold


def uses_compact_surface(config: Config, spec: ModelSpec, *, mutation_ok: bool) -> bool:
    """Bu model sıkı araç yüzeyi mi almalı?"""
    if not mutation_ok:
        return True
    if any(tag.strip().lower() == COMPACT_TAG for tag in spec.tags):
        return True
    if config.runtime.compact_tools_window_tokens <= 0:
        return False
    # Tembel içe aktarma: `context_budget` modülü `execution_policy`'yi, o da bu modülü
    # içe aktarır (döngüsel bağımlılık).
    from .context_budget import context_budget

    return is_weak_model(config, spec, context_budget(config, spec).window_tokens)


def narrow_to_compact_surface(
    names: set[str],
    registry: ToolRegistry,
    *,
    max_external_tools: int | None,
    task_kinds: Collection[str],
    explicit: Collection[str] | None,
) -> set[str]:
    """Sıkı yüzeyde sunulacak araç adlarını daralt (saf: girdiyi değiştirmez)."""
    requested = set(explicit or ())
    hide_desktop = DESKTOP_TASK_KIND not in task_kinds
    kept = {
        name
        for name in names
        if name in requested or not (hide_desktop and name.startswith(COMPACT_HIDDEN_PREFIXES))
    }
    if not max_external_tools:
        return kept
    external = [name for name in registry.names() if name in kept and registry.is_remote(name)]
    over_limit = {name for name in external[max_external_tools:] if name not in requested}
    return kept - over_limit
