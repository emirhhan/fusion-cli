"""Onay kipleri: adlar, Shift+Tab döngüsü, sıkılık sırası (`approval.py`'den ayrıldı)."""

from __future__ import annotations

from enum import Enum


class ApprovalMode(Enum):
    """Kullanıcının seçtiği onay politikası (Claude'un izin kipleri)."""

    AUTO = "auto"
    ACCEPT_EDITS = "edits"
    SECURITY = "security"
    PLAN = "plan"
    BYPASS = "bypass"
    DONT_ASK = "dontAsk"


#: Shift+Tab döngüsü (Claude'daki sıra). "İzinleri atla" BİLEREK yok: tek tuşla
#: yanlışlıkla açılmamalı; `/bypass` ile açıkça seçilir.
CYCLE_MODES = (
    ApprovalMode.AUTO,
    ApprovalMode.SECURITY,
    ApprovalMode.ACCEPT_EDITS,
    ApprovalMode.PLAN,
)


def next_mode(
    mode: ApprovalMode, *, bypass_available: bool = False, auto_available: bool = True
) -> ApprovalMode:
    """Shift+Tab döngüsünde sıradaki kip (Claude, #73/#85).

    Sıra: default → acceptEdits → plan → [bypassPermissions] → [auto] → default. Bypass
    yalnız oturum onunla (ya da `--allow-dangerously-skip-permissions`/kullanıcı ayarı
    `defaultMode: bypassPermissions` ile) başladıysa, auto yalnız `disableAutoMode` yoksa
    döngüdedir. dontAsk hiçbir zaman döngüde değildir.
    """
    cycle = [ApprovalMode.SECURITY, ApprovalMode.ACCEPT_EDITS, ApprovalMode.PLAN]
    if bypass_available:
        cycle.append(ApprovalMode.BYPASS)
    if auto_available:
        cycle.append(ApprovalMode.AUTO)
    if mode not in cycle:
        return cycle[0] if mode is ApprovalMode.AUTO or not auto_available else ApprovalMode.AUTO
    return cycle[(cycle.index(mode) + 1) % len(cycle)]


def may_run_unasked_commands(mode: ApprovalMode) -> bool:
    """Kip, onay sorusu olmadan arka plan komutu (dev sunucusu) çalıştırmaya izin verir mi?

    SECURITY ("okuma dışı her şey sorulur") ve PLAN (hiçbir değişiklik yok) vermez.
    """
    return mode not in (ApprovalMode.SECURITY, ApprovalMode.PLAN, ApprovalMode.DONT_ASK)


#: Kipin elle yazılabilen öteki adları (Claude'daki adlar dahil).
_MODE_ALIASES = {
    "dontask": ApprovalMode.DONT_ASK,
    "dont-ask": ApprovalMode.DONT_ASK,
    "manual": ApprovalMode.SECURITY,
    "manuel": ApprovalMode.SECURITY,
    "default": ApprovalMode.SECURITY,
    "accept-edits": ApprovalMode.ACCEPT_EDITS,
    "acceptedits": ApprovalMode.ACCEPT_EDITS,
    "bypass-permissions": ApprovalMode.BYPASS,
    "bypasspermissions": ApprovalMode.BYPASS,
}


def parse_mode(raw: str) -> ApprovalMode:
    """Kip adını çöz; bilinmiyorsa `ValueError`."""
    value = raw.strip().lower()
    return _MODE_ALIASES.get(value) or ApprovalMode(value)


#: Kiplerin sıkılık sırası (küçük = gevşek). Alt ajanın `permissionMode` alanı üst ajanın
#: kipini yalnız bu sırada YUKARI taşıyabilir (P-034): `bypass` miras alınmaz, `plan`
#: isteyen alt ajan auto kipteki üstten daha gevşek olamaz.
MODE_STRICTNESS: dict[ApprovalMode, int] = {
    ApprovalMode.BYPASS: 0,
    ApprovalMode.AUTO: 1,
    ApprovalMode.ACCEPT_EDITS: 2,
    ApprovalMode.SECURITY: 3,
    ApprovalMode.DONT_ASK: 3,
    ApprovalMode.PLAN: 4,
}


def strictest_mode(parent: ApprovalMode, requested: ApprovalMode | None) -> ApprovalMode:
    """Üst kip ile istenen kipten SIKI olanı döndür; istek yoksa üst kip."""
    if requested is None:
        return parent
    return requested if MODE_STRICTNESS[requested] > MODE_STRICTNESS[parent] else parent
