"""Sandbox ağında liste dışı ana makine: kipe göre karar, soru, kalıcı kural (#323, #347).

Claude Code (sandboxing, "Hosts outside your allowed domains"): Manual/acceptEdits/plan'da
sorulur, bypass'ta ve bypass kullanılabilen plan kipinde izin, auto ve dontAsk'ta red;
strictAllowlist ve deniedDomains her kipte reddeder. Gerçek ağ yok: sahte çözücü.
"""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from fusion_cli.config.permission_rules import PermissionRuleSet, read_rules_file
from fusion_cli.config.sandbox_claude_keys import normalize_claude_sandbox
from fusion_cli.config.sandbox_config import SandboxConfig, sandbox_policy
from fusion_cli.core import sandbox_proxy
from fusion_cli.core.sandbox_policy import SandboxHostGate, SandboxPolicy
from fusion_cli.core.sandbox_proxy import DomainProxy
from fusion_cli.core.shell_sandbox import SHELL_SANDBOX_WRITE_ROOT
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import sandbox_network
from fusion_cli.engines.agent.approval import (
    AcceptEditsApproval,
    ApprovalAnswer,
    AutoApproval,
    BypassApproval,
    DontAskApproval,
    PlanApproval,
    SecurityApproval,
)
from fusion_cli.engines.agent.permission_persist import rule_for_request
from fusion_cli.engines.agent.sandbox_approval import changes_program
from fusion_cli.engines.agent.sandbox_network import NetworkChoice, network_choice


class _Soran:
    def __init__(self, cevap: object) -> None:
        self.cevap = cevap
        self.sorular: list[str] = []

    async def confirm(self, request):
        self.sorular.append(str(request.args["url"]))
        return self.cevap


def _istek(port: int, host: str) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as baglanti:
        baglanti.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
        return baglanti.recv(200)


def _proxy(policy: SandboxPolicy, decider) -> DomainProxy:
    proxy = DomainProxy(policy, resolver=lambda host, port: ["93.184.216.34"], host_decider=decider)
    proxy.start()
    return proxy


def test_kip_tablosu_claude_ile_ayni():
    soran = _Soran(True)
    assert network_choice(BypassApproval(soran)) is NetworkChoice.ALLOW
    assert network_choice(PlanApproval(soran, bypass_available=True)) is NetworkChoice.ALLOW
    assert network_choice(PlanApproval(soran)) is NetworkChoice.ASK
    assert network_choice(SecurityApproval(soran)) is NetworkChoice.ASK
    assert network_choice(AcceptEditsApproval(soran)) is NetworkChoice.ASK
    assert network_choice(AutoApproval(soran)) is NetworkChoice.DENY
    assert network_choice(DontAskApproval()) is NetworkChoice.DENY


def test_bypass_without_prompter_denies_unknown_network_hosts():
    assert network_choice(BypassApproval(None)) is NetworkChoice.DENY
    assert network_choice(PlanApproval(None, bypass_available=True)) is NetworkChoice.DENY


def test_varsayilan_ag_proxyli_ve_auto_allow_acik():
    config = SandboxConfig()
    assert config.network == "allowlist" and config.auto_allow is True
    policy = sandbox_policy(config, home=Path("/h"), root=Path("/r"))
    assert policy.restricts_network and policy.auto_allow and not policy.strict_allowlist


def test_strict_allowlist_claude_adi_okunur():
    data, _ = normalize_claude_sandbox({"network": {"strictAllowlist": True}})
    assert data["strict_allowlist"] is True and data["network"] == "allowlist"


def test_karar_veren_evet_derse_baglanti_gecer_hayirsa_403(monkeypatch):
    gercek = socket.create_connection

    def baglanma(address, *args, **kwargs):
        if address[0] != "127.0.0.1":
            raise OSError("ağ yok (test)")
        return gercek(address, *args, **kwargs)

    monkeypatch.setattr(sandbox_proxy.socket, "create_connection", baglanma)
    policy = SandboxPolicy(network="allowlist")
    for karar, beklenen in ((lambda host: True, b"502"), (lambda host: False, b"403")):
        proxy = _proxy(policy, karar)
        try:
            # Evet: denetim geçer, sahte adrese bağlanamaz (502); hayır: 403.
            assert beklenen in _istek(proxy.port, "yeni.test")
        finally:
            proxy.close()


def test_strict_allowlist_ve_denied_domains_karar_verene_sormaz():
    sorulan: list[str] = []

    def karar(host: str) -> bool:
        sorulan.append(host)
        return True

    for policy, host in (
        (SandboxPolicy(network="allowlist", strict_allowlist=True), "yeni.test"),
        (SandboxPolicy(network="allowlist", denied_domains=("kotu.test",)), "kotu.test"),
    ):
        proxy = _proxy(policy, karar)
        try:
            assert b"403" in _istek(proxy.port, host)
        finally:
            proxy.close()
    assert sorulan == []


def _baglam(tmp_path: Path) -> ToolContext:
    return ToolContext(root=tmp_path, shell_sandbox=SHELL_SANDBOX_WRITE_ROOT)


def _kur_ve_sor(context, policy, host, rules=None):
    async def calis():
        decider = sandbox_network.install_network_gate(context, policy, rules)
        assert decider is not None
        return await asyncio.to_thread(decider, host)

    return asyncio.run(calis())


def test_manual_kipte_sorulur_evet_oturum_boyunca_gecerli(tmp_path):
    context = _baglam(tmp_path)
    soran = _Soran(ApprovalAnswer.SESSION)
    assert _kur_ve_sor(context, SecurityApproval(soran), "pypi.org") is True
    assert soran.sorular == ["https://pypi.org"]
    assert _kur_ve_sor(context, SecurityApproval(soran), "pypi.org") is True
    assert soran.sorular == ["https://pypi.org"]  # ikinci kez sorulmadı
    assert "pypi.org" in context.sandbox_hosts.session_hosts


def test_bir_daha_sorma_yerel_ayara_webfetch_domain_yazar(tmp_path, monkeypatch):
    context = _baglam(tmp_path)
    assert _kur_ve_sor(context, SecurityApproval(_Soran(ApprovalAnswer.ALWAYS)), "pypi.org")
    dosya = tmp_path / ".claude" / "settings.local.json"
    assert "WebFetch(domain:pypi.org)" in json.loads(dosya.read_text())["permissions"]["allow"]
    kurallar = PermissionRuleSet(read_rules_file(dosya))
    # Kural yazılınca bir sonraki oturumda sorulmadan geçer.
    yeni = _baglam(tmp_path)
    soran = _Soran(False)
    assert _kur_ve_sor(yeni, SecurityApproval(soran), "pypi.org", kurallar) is True
    assert soran.sorular == []


def test_hayir_ve_auto_dontask_reddeder_bypass_sormadan_izin(tmp_path):
    soran = _Soran(ApprovalAnswer.DENY)
    assert _kur_ve_sor(_baglam(tmp_path), SecurityApproval(soran), "x.test") is False
    for policy in (AutoApproval(soran), DontAskApproval()):
        assert _kur_ve_sor(_baglam(tmp_path), policy, "y.test") is False
    assert _kur_ve_sor(_baglam(tmp_path), BypassApproval(soran), "z.test") is True
    assert soran.sorular == ["https://x.test"]


def test_sandbox_kapaliyken_karar_veren_kurulmaz(tmp_path):
    context = ToolContext(root=tmp_path)
    context.sandbox_hosts.decider = lambda host: True

    async def calis():
        return sandbox_network.install_network_gate(context, SecurityApproval(_Soran(True)))

    assert asyncio.run(calis()) is None and context.sandbox_hosts.decider is None
    assert isinstance(context.sandbox_hosts, SandboxHostGate)


def test_web_fetch_kalici_kurali_alan_adina_daralir():
    from fusion_cli.engines.agent.sandbox_network import _request

    assert rule_for_request(_request("pypi.org"), None).specifier == "domain:pypi.org"


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("npm test", False),
        ("FOO=bar npm test", True),
        ("make CC=clang", True),
        ('eval "ls"', True),
        ("ls && A=1 make", True),
        ("make all", False),
    ],
)
def test_program_degistiren_bicimler_auto_allow_disinda(komut, beklenen):
    assert changes_program(komut) is beklenen
