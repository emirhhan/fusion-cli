"""`run_shell` sandbox çalışma anı: plan, ağ proxy'si, ortam ve sonuç notları (P-010).

`core.shell_sandbox` saf planlayıcıdır; burada bağlamdan politika okunur, gerekiyorsa
alan adı proxy'si başlatılır ve komut bittikten sonra modele eyleme dönük not üretilir
(engellenen yazma/okuma, engellenen alan adı, sandbox dışı çalıştırma).

Sandbox dışı çalıştırma iki yoldan olur ve ikisi de onay akışından geçer
(`engines.agent.sandbox_approval`): model `unsandboxed=true` ister (her seferinde açık
onay; `sandbox.allow_unsandboxed=false` ise istek yok sayılır) ya da komut
`sandbox.excluded_commands` önekiyle başlar (normal onay).
"""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ..core.redaction import is_secret_env_name
from ..core.sandbox_policy import SandboxPolicy, is_excluded_command
from ..core.sandbox_proxy import DomainProxy
from ..core.shell_sandbox import (
    SHELL_SANDBOX_WRITE_ROOT,
    ProxyEndpoint,
    SandboxPlan,
    plan_shell_sandbox,
    temporary_roots,
)
from ..core.tools import ToolArgs, ToolContext

__all__ = [
    "OUTSIDE_EXCLUDED",
    "OUTSIDE_REQUESTED",
    "SandboxRun",
    "delete_blocked",
    "outside_reason",
    "prepare_sandbox",
    "probe_plan",
    "sandbox_env",
    "sandbox_notes",
]

_LOG = logging.getLogger(__name__)

#: `run_shell` argümanı: sandbox dışında çalıştırma isteği.
UNSANDBOXED_ARG = "unsandboxed"
OUTSIDE_REQUESTED = "istek"
OUTSIDE_EXCLUDED = "liste"
#: Kabukların ağ hatası belirtileri (ağ kapalıyken ipucu vermek için).
_NETWORK_FAILURE_MARKERS = (
    "Could not resolve host",
    "Couldn't connect",
    "nodename nor servname",
    "Name or service not known",
    "Temporary failure in name resolution",
    "Network is unreachable",
    "getaddrinfo",
    "ENOTFOUND",
)


@dataclass(slots=True)
class SandboxRun:
    """Tek komutun sandbox durumu; çalıştırmadan önce kurulur, sonra notları üretir."""

    plan: SandboxPlan
    policy: SandboxPolicy
    outside: str | None = None
    proxy: DomainProxy | None = None
    mark: int = 0
    notices: list[str] = field(default_factory=list)


class _ProxyPool:
    """Politika başına tek proxy; süreç boyunca yaşar.

    Bilinçli süreç-kapsamlı durum (`shell._SHOWN_SANDBOX_NOTICES` gibi): arka plan işi
    turdan sonra da ağ isteyebilir, proxy tur bağlamıyla birlikte ölürse iş kopardı.
    Thread'ler daemon'dur; süreç kapanınca dinleyici de kapanır.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proxies: dict[tuple[tuple[str, ...], tuple[str, ...], bool], DomainProxy] = {}

    def get(self, policy: SandboxPolicy, *, unix: bool) -> DomainProxy:
        key = (policy.allowed_domains, policy.denied_domains, unix)
        with self._lock:
            proxy = self._proxies.get(key)
            if proxy is None:
                path = Path(tempfile.mkdtemp(prefix="fusion-sbx-")) / "proxy.sock" if unix else None
                proxy = DomainProxy(policy, unix_path=path)
                proxy.start()
                self._proxies[key] = proxy
            return proxy


_PROXIES = _ProxyPool()


def outside_reason(command: str, args: ToolArgs, context: ToolContext) -> str | None:
    """Komut sandbox DIŞINDA mı çalışacak? (`istek` | `liste` | None)

    Sandbox kapalıysa None. Onay katmanı ve çalıştırıcı aynı kararı buradan okur.
    """
    if getattr(context, "shell_sandbox", "off") != SHELL_SANDBOX_WRITE_ROOT:
        return None
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    if args.get(UNSANDBOXED_ARG) is True and policy.allow_unsandboxed:
        return OUTSIDE_REQUESTED
    if is_excluded_command(command, policy.excluded_commands):
        return OUTSIDE_EXCLUDED
    return None


def _proxy(policy: SandboxPolicy, notices: list[str]) -> DomainProxy | None:
    if not (policy.restricts_network and policy.allowed_domains):
        return None
    try:
        return _PROXIES.get(policy, unix=sys.platform.startswith("linux"))
    except OSError as error:
        _LOG.warning("sandbox proxy başlatılamadı", extra={"hata": str(error)})
        notices.append(f"Sandbox ağ proxy'si başlatılamadı ({error}); dış ağ tamamen kapalı.")
        return None


def prepare_sandbox(command: str, args: ToolArgs, context: ToolContext) -> SandboxRun:
    """Komutun sandbox planını kur (gerekiyorsa proxy'yi başlat)."""
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    mode = getattr(context, "shell_sandbox", "off")
    outside = outside_reason(command, args, context)
    run = SandboxRun(plan=SandboxPlan(), policy=policy, outside=outside)
    if mode != SHELL_SANDBOX_WRITE_ROOT or outside is not None:
        return run
    if args.get(UNSANDBOXED_ARG) is True:
        run.notices.append(
            "unsandboxed=true yok sayıldı: sandbox.allow_unsandboxed kapalı; komut sandbox içinde."
        )
    run.proxy = _proxy(policy, run.notices)
    endpoint = (
        ProxyEndpoint(port=run.proxy.port, unix_path=run.proxy.unix_path)
        if run.proxy is not None
        else None
    )
    run.plan = plan_shell_sandbox(
        mode, (context.root, *context.extra_roots), policy=policy, proxy=endpoint
    )
    run.mark = run.proxy.mark() if run.proxy is not None else 0
    return run


def probe_plan(context: ToolContext) -> SandboxPlan:
    """Proxy BAŞLATMADAN plan: sandbox kurulabilir mi, kurulamıyorsa ne olur? (onay, durum)."""
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    return plan_shell_sandbox(
        getattr(context, "shell_sandbox", "off"),
        (context.root, *context.extra_roots),
        policy=policy,
    )


def delete_blocked(targets: list[str], args: ToolArgs, context: ToolContext) -> str | None:
    """Sandbox açıkken sade `rm` hedefi yazılabilir köklerin dışındaysa gerekçe.

    Sade `rm` sandbox'ta değil Fusion sürecinde çöpe taşınır (`shell._guarded_delete`);
    bu denetim olmadan `rm ../dis/dosya` sandbox'ın yazma sınırını atlatırdı.
    """
    if getattr(context, "shell_sandbox", "off") != SHELL_SANDBOX_WRITE_ROOT:
        return None
    if outside_reason(" ".join(["rm", *targets]), args, context) is not None:
        return None
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    allowed = tuple(
        path.resolve()
        for path in (context.root, *context.extra_roots, *policy.extra_write, *temporary_roots())
    )
    for raw in targets:
        target = Path(raw).expanduser()
        resolved = (target if target.is_absolute() else context.root / target).resolve()
        if not any(resolved == base or base in resolved.parents for base in allowed):
            return (
                f"Sandbox açık: {raw} yazılabilir köklerin dışında, silinmedi "
                "(runtime.shell_sandbox=write_root). Gerekliyse sandbox.allow_write ya da "
                "--add-dir."
            )
    return None


def sandbox_env(base: dict[str, str], run: SandboxRun) -> dict[str, str]:
    """Komut ortamı: sandbox içindeyse sır gibi görünen adlar çıkar, proxy adresi eklenir."""
    if not run.plan.is_active:
        return base
    env = (
        {name: value for name, value in base.items() if not is_secret_env_name(name)}
        if run.plan.hide_secret_env
        else dict(base)
    )
    env.update(dict(run.plan.env))
    return env


def sandbox_notes(run: SandboxRun, returncode: int, stderr: str) -> list[str]:
    """Komuttan sonra modele gidecek notlar (bir kez gösterilecek uyarılar hariç)."""
    notes = list(run.notices)
    if run.outside == OUTSIDE_REQUESTED:
        notes.append("Komut kullanıcı onayıyla sandbox DIŞINDA çalıştı.")
    elif run.outside == OUTSIDE_EXCLUDED:
        notes.append(
            "Komut sandbox dışı listesinde (sandbox.excluded_commands); sandbox'sız çalıştı."
        )
    if not run.plan.is_active:
        return notes
    if returncode != 0 and "Operation not permitted" in stderr:
        notes.append(_denied_hint(run.policy))
    if run.proxy is not None:
        hosts = list(dict.fromkeys(item.host for item in run.proxy.denials_since(run.mark)))
        if hosts:
            notes.append(
                f"Sandbox ağı engelledi: {', '.join(hosts)}. Gerekliyse kullanıcı izin verir: "
                f"/sandbox izin {hosts[0]}"
            )
    elif (
        run.policy.restricts_network
        and returncode != 0
        and any(marker in stderr for marker in _NETWORK_FAILURE_MARKERS)
    ):
        notes.append(
            "Sandbox ağı kapalı (sandbox.network=allowlist, izinli alan adı yok). "
            "Gerekliyse kullanıcı izin verir: /sandbox izin <alan-adı>"
        )
    return notes


def _denied_hint(policy: SandboxPolicy) -> str:
    hint = (
        "Komut sandbox içinde çalışıyor (runtime.shell_sandbox=write_root): yazma yalnız proje "
        "kökü, --add-dir, sandbox.allow_write ve geçici dizinlere açık; sandbox.deny_read "
        "yolları okunamaz."
    )
    if policy.allow_unsandboxed:
        hint += (
            " Gerçekten gerekiyorsa run_shell(unsandboxed=true) ile yeniden dene "
            "(kullanıcı onaylar)."
        )
    return hint
