"""`run_shell` sandbox çalışma anı: plan, ağ proxy'si, ortam ve sonuç notları (P-010).

`core.shell_sandbox` saf planlayıcıdır; burada bağlamdan politika okunur, gerekiyorsa
alan adı proxy'si başlatılır ve komut bittikten sonra modele eyleme dönük not üretilir
(engellenen yazma/okuma, engellenen alan adı, sandbox dışı çalıştırma).

Proxy KOMUT başınadır ve sahibine bağlıdır: ön plan komutu bitince, arka plan işi ise
süreci bitince `release_sandbox` ile kapanır. Ölçüldü (1 Kasım): proxy politika başına
süreç boyunca paylaşılıyordu; eşzamanlı komutların (arka plan işi, alt ajan) engellenen
adları birbirinin notuna düşüyor, `/sandbox izin` sonrası eski proxy süreç kapanana
kadar açık kalıyordu.

Sandbox dışı çalıştırma iki yoldan olur ve ikisi de onay akışından geçer
(`engines.agent.sandbox_approval`): model `unsandboxed=true` ister (her seferinde açık
onay; `sandbox.allow_unsandboxed=false` ise istek yok sayılır) ya da komut
`sandbox.excluded_commands` önekiyle başlar (normal onay).
"""

from __future__ import annotations

import contextlib
import logging
import sys
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.redaction import is_secret_env_name
from ..core.sandbox_forward import UnixForwarder
from ..core.sandbox_policy import (
    PROTECTED_ANCHORS,
    SandboxPolicy,
    normalize_domain,
)
from ..core.sandbox_proxy import DomainProxy, HostDecider
from ..core.shell_sandbox import (
    SHELL_SANDBOX_WRITE_ROOT,
    ProxyEndpoint,
    SandboxPlan,
    plan_shell_sandbox,
    temporary_roots,
)
from ..core.tools import ToolArgs, ToolContext
from .sandbox_cdp import fusion_debug_ports
from .sandbox_excluded import is_excluded
from .sandbox_mask import apply_masks, prepare_tls

if TYPE_CHECKING:
    from .sandbox_ca import SessionCa

__all__ = [
    "OUTSIDE_EXCLUDED",
    "OUTSIDE_REQUESTED",
    "SandboxRun",
    "background_exit_note",
    "delete_blocked",
    "outside_reason",
    "prepare_sandbox",
    "probe_plan",
    "release_sandbox",
    "sandbox_env",
    "sandbox_notes",
]

_LOG = logging.getLogger(__name__)

#: `run_shell` argümanı: sandbox dışında çalıştırma isteği.
UNSANDBOXED_ARG = "unsandboxed"
#: Claude Code'daki parametre adı (#351); eski `unsandboxed` takma ad olarak okunur.
DISABLE_SANDBOX_ARG = "dangerouslyDisableSandbox"


def asks_unsandboxed(args: ToolArgs) -> bool:
    """Çağrı sandbox dışında yeniden deneme istiyor mu (Claude adı ya da eski ad)?"""
    return args.get(DISABLE_SANDBOX_ARG) is True or args.get(UNSANDBOXED_ARG) is True


#: Prob planındaki sahte proxy soketi (açılmaz; yalnız "proxy gerekir" bilgisini taşır).
_PROBE_SOCKET = Path(tempfile.gettempdir()) / "fusion-sandbox-prob" / "proxy.sock"
OUTSIDE_REQUESTED = "istek"
OUTSIDE_EXCLUDED = "liste"
#: Başarısız komut notunda adıyla gösterilen gizli değişken sayısı.
_HIDDEN_ENV_SHOWN = 6
#: Ağ ret notunda gösterilen alan adı sayısı.
_DENIED_HOSTS_SHOWN = 5
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
    #: Sandbox ortamından çıkarılan sır görünümlü ADLAR (değerler değil).
    hidden_env: tuple[str, ...] = ()
    #: Kullanıcının kendi proxy'sine Linux aktarıcıları (`httpProxyPort`/`socksProxyPort`).
    forwarders: list[UnixForwarder] = field(default_factory=list)
    #: `tlsTerminate` CA'sı (sandbox ortamına güven değişkenleri eklenir; #350, #368).
    tls: SessionCa | None = None


def _uses_unix_proxy() -> bool:
    """Linux'ta proxy Unix soketidir (ağ ad alanına bağlanır); macOS'ta loopback portu."""
    return sys.platform.startswith("linux")


def outside_reason(command: str, args: ToolArgs, context: ToolContext) -> str | None:
    """Komut sandbox DIŞINDA mı çalışacak? (`istek` | `liste` | None)

    Sandbox kapalıysa None. Onay katmanı ve çalıştırıcı aynı kararı buradan okur.
    """
    if getattr(context, "shell_sandbox", "off") != SHELL_SANDBOX_WRITE_ROOT:
        return None
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    if asks_unsandboxed(args) and policy.allow_unsandboxed:
        return OUTSIDE_REQUESTED
    if is_excluded(command, policy.excluded_commands, context.root):
        return OUTSIDE_EXCLUDED
    return None


def _proxy(
    policy: SandboxPolicy,
    notices: list[str],
    decider: HostDecider | None = None,
    tls: SessionCa | None = None,
) -> DomainProxy | None:
    """Bu komuta özel proxy (sahibi `release_sandbox` ile kapatır).

    Claude gibi ağ kısıtlıyken trafik HER ZAMAN proxy'den geçer: liste boş olsa da liste dışı
    ad kipe göre sorulur (`decider`, #323). Karar veren yoksa ve liste boşsa proxy kurulmaz
    (dış ağ tamamen kapalı; eski davranış).
    """
    if (
        not policy.restricts_network
        or policy.external_proxy
        or not (policy.allowed_domains or decider is not None)
    ):
        return None
    path = (
        Path(tempfile.mkdtemp(prefix="fusion-sbx-")) / "proxy.sock" if _uses_unix_proxy() else None
    )
    proxy = DomainProxy(
        policy,
        unix_path=path,
        blocked_ports=fusion_debug_ports,
        host_decider=decider,
        tls=tls,
        plaintext_inject=policy.allow_plaintext_inject,
    )
    try:
        proxy.start()
        return proxy
    except OSError as error:
        _remove_socket_dir(path)
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
    if asks_unsandboxed(args):
        run.notices.append(
            "dangerouslyDisableSandbox=true yok sayıldı: sandbox.allowUnsandboxedCommands "
            "kapalı; komut sandbox içinde."
        )
    # Fusion Chrome'larının CDP portları her kipte kapalı (Seatbelt; proxy her bağlantıda bakar).
    policy = replace(policy, denied_local_ports=fusion_debug_ports())
    policy, run.tls = prepare_tls(policy, run.notices)
    run.policy = policy
    gate = getattr(context, "sandbox_hosts", None)
    run.proxy = _proxy(policy, run.notices, getattr(gate, "decider", None), run.tls)
    endpoint = (
        ProxyEndpoint(port=run.proxy.port, unix_path=run.proxy.unix_path)
        if run.proxy is not None
        else _external_endpoint(policy, run)
    )
    run.plan = plan_shell_sandbox(
        mode, (context.root, *context.extra_roots), policy=policy, proxy=endpoint
    )
    run.mark = run.proxy.mark() if run.proxy is not None else 0
    return run


def _external_endpoint(policy: SandboxPolicy, run: SandboxRun) -> ProxyEndpoint | None:
    """Claude `httpProxyPort`/`socksProxyPort` (#350): trafik kullanıcının proxy'sine gider.

    Fusion proxy'si başlatılmaz; alan adı listeleri ve ağ soruları bu trafiğe uygulanmaz
    (süzme kullanıcının proxy'sindedir). Linux'ta port, ad alanına Unix soketiyle taşınır.
    """
    if not policy.restricts_network or not policy.external_proxy:
        return None
    if not _uses_unix_proxy():
        return ProxyEndpoint(port=policy.http_proxy_port, socks_port=policy.socks_proxy_port)
    paths: dict[str, Path | None] = {"http": None, "socks": None}
    for name, port in (("http", policy.http_proxy_port), ("socks", policy.socks_proxy_port)):
        if not port:
            continue
        forwarder = UnixForwarder(
            Path(tempfile.mkdtemp(prefix="fusion-sbx-")) / f"{name}.sock", port
        )
        try:
            forwarder.start()
        except OSError as error:
            run.notices.append(f"Proxy aktarıcısı başlatılamadı ({error}); dış ağ kapalı.")
            continue
        run.forwarders.append(forwarder)
        paths[name] = forwarder.unix_path
    return ProxyEndpoint(unix_path=paths["http"], socks_unix_path=paths["socks"])


def _remove_socket_dir(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            path.parent.rmdir()


def release_sandbox(run: SandboxRun) -> None:
    """Komutun proxy'sini kapat (Linux'ta soket dizini de silinir); ikinci çağrı zararsız."""
    for forwarder in run.forwarders:
        forwarder.close()
        _remove_socket_dir(forwarder.unix_path)
    run.forwarders.clear()
    if run.proxy is None:
        return
    run.proxy.close()
    _remove_socket_dir(run.proxy.unix_path)


def background_exit_note(run: SandboxRun) -> str:
    """Arka plan işi bitince günlüğe eklenecek ağ ret notu; proxy de kapatılır."""
    try:
        hosts = _denied_hosts(run.proxy, run.mark) if run.proxy is not None else []
    finally:
        release_sandbox(run)
    return f"FUSION_NOT: {_denied_note(hosts)}\n" if hosts else ""


def probe_plan(context: ToolContext) -> SandboxPlan:
    """Proxy BAŞLATMADAN plan: sandbox kurulabilir mi, kurulamıyorsa ne olur? (onay, durum).

    Proxy gerekecekse sahte uçla planlanır; böylece gerçek çalıştırmadaki denetimler
    (Linux'ta socat) burada da yapılır. Ölçüldü (31 Ekim): socat yokken prob proxy'siz
    planlayıp "aktif" diyordu, `auto_allow` sormadan onaylıyordu, gerçek plan ise
    kurulamayıp komut sandbox'sız ve ağı açık koşuyordu.
    """
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    probe = (
        ProxyEndpoint(port=1, unix_path=_PROBE_SOCKET)
        if policy.restricts_network and (policy.allowed_domains or policy.external_proxy)
        else None
    )
    return plan_shell_sandbox(
        getattr(context, "shell_sandbox", "off"),
        (context.root, *context.extra_roots),
        policy=policy,
        proxy=probe,
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
    if policy.filesystem_disabled:
        return None  # Claude `filesystem.disabled`: yazma sınırı yok (#350)
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
    """Komut ortamı: sandbox içindeyse `credentials.envVars` adları (ve eski `hide_secret_env`
    açıksa sır gibi görünen adlar) çıkar, proxy adresi eklenir."""
    if not run.plan.is_active:
        return base
    denied = set(run.policy.deny_env)
    env = {
        name: value
        for name, value in base.items()
        if name not in denied and not (run.plan.hide_secret_env and is_secret_env_name(name))
    }
    run.hidden_env = tuple(sorted(name for name in base if name not in env))
    # Claude mask (#368): komut yer tutucuyu görür; proxy gerçek değeri izinli adlara koyar.
    env, injections = apply_masks(env, run.policy)
    if run.proxy is not None:
        run.proxy.set_injections(injections)
    env.update(dict(run.plan.env))
    if run.tls is not None and run.proxy is not None:
        env.update(run.tls.trust_env())
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
        notes.append(_denied_hint(run.policy, stderr))
    if returncode != 0 and run.hidden_env:
        # Eski write_root kullanıcısı yükseltmede belirteç bekleyen komutun (gh, npm publish)
        # neden düştüğünü görsün. Ölçüldü (31 Ekim): gizlenen ad için hiç not yoktu.
        names = ", ".join(run.hidden_env[:_HIDDEN_ENV_SHOWN])
        more = len(run.hidden_env) - _HIDDEN_ENV_SHOWN
        notes.append(
            f"Sandbox'ta gizlenen ortam değişkenleri: {names}{f' (+{more})' if more > 0 else ''}. "
            "Komut bunlara ihtiyaç duyuyorsa kullanıcı açar: sandbox.hide_secret_env=false."
        )
    if run.proxy is not None:
        hosts = _denied_hosts(run.proxy, run.mark)
        if hosts:
            notes.append(_denied_note(hosts))
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


def _denied_note(hosts: list[str]) -> str:
    return (
        f"Sandbox ağı engelledi: {', '.join(hosts)}. Gerekliyse kullanıcı izin verir: "
        f"/sandbox izin {hosts[0]}"
    )


def _denied_hosts(proxy: DomainProxy, mark: int) -> list[str]:
    """Engellenen adlar, yalnız geçerli alan adı/IP biçiminde (kanonik, en çok 5).

    Ad, sandbox içindeki istemcinin yazdığı ham metindir; modele giden nota yalnız
    `normalize_domain`'den geçen biçim girer. Ölçüldü (31 Ekim): `CONNECT` satırındaki
    rastgele metin "/sandbox izin <metin>" önerisi olarak modele dönüyordu.
    """
    hosts = (normalize_domain(item.host) for item in proxy.denials_since(mark))
    return list(dict.fromkeys(host for host in hosts if host is not None))[:_DENIED_HOSTS_SHOWN]


def _denied_hint(policy: SandboxPolicy, stderr: str = "") -> str:
    hint = (
        "Komut sandbox içinde çalışıyor (runtime.shell_sandbox=write_root): yazma yalnız proje "
        "kökü, --add-dir, sandbox.allow_write ve geçici dizinlere açık; sandbox.deny_read "
        "yolları okunamaz."
    )
    if any(f"{anchor}/" in stderr or f"{anchor}:" in stderr for anchor in PROTECTED_ANCHORS):
        hint += (
            " .git/config, .git/hooks, .claude/.fusion ayar dosyaları ve .mcp.json sandbox "
            "içinden hiç yazılamaz (git init, git remote add, git push -u bunlara yazar)."
        )
    if policy.allow_unsandboxed:
        hint += (
            " Gerçekten gerekiyorsa run_shell(dangerouslyDisableSandbox=true) ile yeniden dene "
            "(kullanıcı onaylar)."
        )
    return hint
