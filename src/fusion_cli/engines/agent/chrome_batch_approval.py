"""`chrome_batch` onayı: her öğenin kendi izin denetimi (#432; Claude `browser_batch`).

Claude: "Each tool's own permission check runs per item". Fusion'da toplu çağrı tek kartla
sorulur ama karar öğelerden kurulur:

- Bir öğe `deny` kuralına, yasak eyleme ya da yükleme okuma kuralına takılırsa bütün çağrı
  sorulmadan kapanır (gerekçe öğeyle birlikte).
- Bir öğede `ask` kuralı varsa çağrı her kipte sorulur.
- Etki en sıkı öğenin etkisidir; tehlike notu (yetki verme, hassas alan) korunur, böyle bir
  çağrı oturum iznine dönüşmez.
- Yalnız tüm öğeler salt okunursa çağrı okuma sayılır (plan kipi izin verir).
- Plan kipinde istem çıkaran öğe (#450: GIF kaydı, yeni sekme/pencere, kısayol) toplu çağrıyı
  da istemli yapar (belge: "including batch calls that contain them").

Öğelerin etkisi onay anındaki sayfaya göre hesaplanır; önceki öğe sayfayı değiştirirse
çalışma anı denetimi `tools.chrome_script.chrome_batch` içindedir.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ...core.tools import Tool, ToolArgs, ToolEffect
from ...tools.chrome_script import BATCH_TOOL, batch_items, batch_tool

if TYPE_CHECKING:
    from .approval import ApprovalRequest

__all__ = ["BATCH_TOOL", "apply_batch"]

#: Öğe isteğini kuran çağrı (`approval.resolve_request`, döngüsel içe aktarma olmasın diye verilir).
ItemResolver = Callable[[Tool, ToolArgs], Awaitable["ApprovalRequest"]]

_RANK = {
    ToolEffect.LOCAL: 0,
    ToolEffect.REMOTE_READ: 1,
    ToolEffect.REMOTE_INTERACT: 2,
    ToolEffect.REMOTE_WRITE: 3,
    ToolEffect.REMOTE_DESTRUCTIVE: 5,
}
#: Tabloda olmayan etki (oturum profili vb.) yazmadan sıkı, yıkıcıdan gevşek sayılır.
_UNKNOWN_RANK = 4


def _rank(effect: ToolEffect) -> int:
    return _RANK.get(effect, _UNKNOWN_RANK)


def _is_read(sub: ApprovalRequest) -> bool:
    return sub.read_only or (not sub.tool.mutating and _rank(sub.effect) <= 1)


async def apply_batch(
    request: ApprovalRequest, args: ToolArgs, resolve: ItemResolver
) -> ApprovalRequest:
    """Toplu çağrının isteğini öğelerin istekleriyle birleştir."""
    items = batch_items(args)
    if isinstance(items, str):
        return replace(request, pre_denied=request.pre_denied or items)
    subs: list[tuple[int, str, ApprovalRequest]] = []
    for index, (name, data) in enumerate(items, start=1):
        tool = batch_tool(name)
        if tool is None:
            return replace(request, pre_denied=f"{index}. öğe: '{name}' aracı yok.")
        sub = await resolve(tool, data)
        if sub.pre_denied is not None:
            return replace(
                request, pre_denied=request.pre_denied or f"{index}. öğe ({name}): {sub.pre_denied}"
            )
        subs.append((index, name, sub))
    return _merge(request, subs)


def _merge(
    request: ApprovalRequest, subs: list[tuple[int, str, ApprovalRequest]]
) -> ApprovalRequest:
    # Etki öğelerden gelir: toplu aracın kendi etkisi yalnız yer tutucudur. Değiştirmeyen öğe
    # (chrome_page) onaya hiç girmez; hepsi böyleyse toplu çağrı okumadır.
    strictest = max((sub for _, _, sub in subs), key=lambda sub: _rank(sub.effect))
    reading = all(_is_read(sub) for _, _, sub in subs)
    effect = ToolEffect.REMOTE_READ if reading else strictest.effect
    danger = next((sub.danger for _, _, sub in subs if sub.danger), None)
    pre_ask = next(
        (f"{index}. öğe ({name}): {sub.pre_ask}" for index, name, sub in subs if sub.pre_ask),
        None,
    )
    risks = [f"{index}. {name}: {sub.risk}" for index, name, sub in subs if sub.risk]
    notes = [f"{index}. {name}: {sub.note}" for index, name, sub in subs if sub.note]
    return replace(
        request,
        effect=effect,
        danger=request.danger or danger,
        pre_ask=request.pre_ask or pre_ask,
        risk="; ".join(risks) or request.risk,
        note="; ".join(notes) or request.note,
        read_only=reading,
        unattended_safe=all(sub.unattended_safe for _, _, sub in subs),
        rule=request.rule or next((sub.rule for _, _, sub in subs if sub.rule), None),
        plan_prompt=request.plan_prompt or any(sub.plan_prompt for _, _, sub in subs),
        **_site_consent(subs),
    )


def _site_consent(subs: list[tuple[int, str, ApprovalRequest]]) -> dict[str, Any]:
    """Değiştiren öğelerin hepsi aynı site iznini taşıyorsa toplu çağrı da onu taşır (#435).

    Farklı anahtar ya da anahtarsız değiştiren öğe varsa izin hatırlanmaz (her seferinde sorulur).
    """
    acting = [sub for _, _, sub in subs if not _is_read(sub)]
    keys = {sub.consent_key for sub in acting}
    if len(keys) != 1 or None in keys:
        return {}
    return {"consent_key": acting[0].consent_key, "chrome_site": acting[0].chrome_site}
