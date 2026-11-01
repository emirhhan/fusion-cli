"""`run_shell` sandbox politikası (P-010): okuma engeli, ek yazma kökü, Linux bubblewrap,
fail_if_unavailable, sır ortamı, sandbox dışı çalıştırma onayı ve yapılandırma.

Ölçüldü (31 Ekim, e30d57a0): `write_root` açıkken `cat ~/.ssh/id_rsa` okunuyordu, `rm
../dis/x` sandbox'ı atlayıp Fusion sürecinde çöpe taşınıyordu, Linux'ta sandbox yoktu ve
`OPENAI_API_KEY` sandbox'lı komutun `env` çıktısına düşüyordu.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from fusion_cli.config import trust
from fusion_cli.config.loader import load_config
from fusion_cli.config.paths import bundled_defaults
from fusion_cli.config.sandbox_config import SandboxConfig, sandbox_policy, validate_sandbox
from fusion_cli.config.settings_access import apply_setting, read_setting, write_setting
from fusion_cli.core import shell_sandbox
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.sandbox_policy import (
    SandboxPolicy,
    domain_allowed,
    normalize_domain,
)
from fusion_cli.core.shell_sandbox_linux import LINUX_BRIDGE_PORT, LinuxTools
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMode,
    Decision,
    build_policy,
    resolve_request,
)
from fusion_cli.tools import shell
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.sandbox_excluded import is_excluded

_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


def _sandbox_calisir() -> bool:
    if sys.platform != "darwin" or not _SANDBOX_EXEC.exists():
        return False
    probe = subprocess.run(
        [str(_SANDBOX_EXEC), "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


macos_sandbox = pytest.mark.skipif(not _sandbox_calisir(), reason="sandbox-exec kullanılamıyor")


def _context(root: Path, policy: SandboxPolicy | None = None, **extra: object) -> ToolContext:
    return ToolContext(root=root, shell_sandbox="write_root", sandbox_policy=policy, **extra)  # type: ignore[arg-type]


@pytest.fixture
def proje(tmp_path, monkeypatch):
    """Geçici dizin izni kaldırılır: tmp_path kardeşleri kök dışı sayılsın."""
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    root = tmp_path / "proje"
    root.mkdir()
    (tmp_path / "disari").mkdir()
    return root


# --- saf kurallar ---------------------------------------------------------- #


def test_alan_adi_normallesir_ve_gecersiz_reddedilir():
    assert normalize_domain(" GitHub.com. ") == "github.com"
    assert normalize_domain("*.npmjs.org") == "*.npmjs.org"
    assert normalize_domain("[::1]") == "::1"
    assert normalize_domain("http://x.com") is None
    assert normalize_domain("a b") is None


def test_yasak_liste_izin_listesinden_ustundur_ve_joker_alt_alan_adidir():
    policy = SandboxPolicy(
        allowed_domains=("github.com", "*.githubusercontent.com"),
        denied_domains=("gist.githubusercontent.com",),
    )
    assert domain_allowed("github.com", policy)
    assert not domain_allowed("api.github.com", policy)
    assert domain_allowed("raw.githubusercontent.com", policy)
    assert not domain_allowed("githubusercontent.com", policy)
    assert not domain_allowed("gist.githubusercontent.com", policy)


def test_sandbox_disi_liste_claude_bash_kural_soz_dizimiyle_eslesir():
    """#367: `x *` argümanlı/argümansız eşler; zincirde HER komut uyarsa dışarıda çalışır."""
    desenler = ("docker *", "Bash(git push *)", "Bash(npm test)")
    assert is_excluded("docker", desenler) and is_excluded("docker ps -a", desenler)
    assert is_excluded("git push origin main", desenler)
    assert is_excluded("docker build . && docker push x", desenler)
    assert is_excluded("npm test", desenler) and not is_excluded("npm test -- -x", desenler)
    assert not is_excluded("git pull", desenler)
    assert not is_excluded("docker ps && curl evil.example", desenler)
    assert not is_excluded("docker ps | sh", desenler)
    assert not is_excluded("dockerx ps", desenler)
    assert not is_excluded("unshare docker ps", ("unshare *", "docker *"))


def test_sandbox_disi_eski_yildizsiz_onek_takma_ad():
    assert is_excluded("docker ps -a", ("docker",)) and is_excluded("git push", ("git push",))


# --- macOS profili ---------------------------------------------------------- #


def test_okuma_engeli_ve_ek_kok_profile_parametreyle_girer(tmp_path):
    gizli = tmp_path / 'gizli") (allow file-read*'
    policy = SandboxPolicy(deny_read=(gizli,), extra_write=(tmp_path / "ek",))
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), policy=policy, platform="darwin", executable=str(_SANDBOX_EXEC)
    )
    profil = plan.prefix[plan.prefix.index("-p") + 1]
    assert str(gizli) not in profil
    assert '(deny file-read* (subpath (param "R0")))' in profil
    assert f"R0={gizli.resolve()}" in plan.prefix
    assert f"W1={(tmp_path / 'ek').resolve()}" in plan.prefix


def test_ag_allowlist_profili_yalniz_proxy_portuna_izin_verir(tmp_path):
    policy = SandboxPolicy(network="allowlist", allowed_domains=("x.com",), allow_localhost=False)
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=policy,
        platform="darwin",
        executable=str(_SANDBOX_EXEC),
        proxy=shell_sandbox.ProxyEndpoint(port=41234),
    )
    profil = plan.prefix[plan.prefix.index("-p") + 1]
    assert "(deny network*)" in profil
    assert '(remote ip "localhost:41234")' in profil
    assert "localhost:*" not in profil
    assert ("HTTPS_PROXY", "http://127.0.0.1:41234") in plan.env
    assert ("NO_PROXY", "") in plan.env


def test_ag_acik_kipte_ag_kurali_ve_proxy_ortami_yok(tmp_path):
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=SandboxPolicy(network="open"),
        platform="darwin",
        executable=str(_SANDBOX_EXEC),
    )
    assert "network" not in plan.prefix[-1] and plan.env == ()


def test_fail_if_unavailable_plani_reddeder(tmp_path):
    policy = SandboxPolicy(fail_if_unavailable=True)
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), policy=policy, platform="win32"
    )
    assert plan.prefix == () and "çalıştırılmadı" in plan.refused


# --- Linux bubblewrap ------------------------------------------------------- #


def test_linux_bwrap_kok_salt_okunur_yazma_kokleri_bagli(tmp_path):
    gizli = tmp_path / "ssh"
    gizli.mkdir()
    dosya = tmp_path / "netrc"
    dosya.write_text("x")
    policy = SandboxPolicy(deny_read=(gizli, dosya, tmp_path / "yok"), network="open")
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=policy,
        platform="linux",
        linux_tools=LinuxTools(bwrap="/usr/bin/bwrap"),
    )
    argv = list(plan.prefix)
    assert argv[:2] == ["/usr/bin/bwrap", "--die-with-parent"]
    baslangic = argv.index("--ro-bind")
    assert argv[baslangic : baslangic + 3] == ["--ro-bind", "/", "/"]
    kok = str(tmp_path.resolve())
    assert ["--bind", kok, kok] == argv[argv.index(kok) - 1 : argv.index(kok) + 2]
    assert ["--tmpfs", str(gizli)] == argv[argv.index(str(gizli)) - 1 : argv.index(str(gizli)) + 1]
    assert ["--ro-bind", "/dev/null", str(dosya)] == argv[
        argv.index(str(dosya)) - 2 : argv.index(str(dosya)) + 1
    ]
    assert str(tmp_path / "yok") not in argv
    assert "--unshare-net" not in argv and argv[-1] == "--"


def test_linux_allowlist_bos_listede_ag_ad_alani_kapali_kopru_yok(tmp_path):
    policy = SandboxPolicy(network="allowlist")
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), policy=policy, platform="linux", linux_tools=LinuxTools("/b")
    )
    assert "--unshare-net" in plan.prefix and plan.prefix[-1] == "--" and plan.env == ()


def test_linux_allowlist_socat_koprusu_ve_proxy_ortami(tmp_path):
    soket = tmp_path / "sbx" / "proxy.sock"
    policy = SandboxPolicy(network="allowlist", allowed_domains=("pypi.org",))
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=policy,
        platform="linux",
        linux_tools=LinuxTools("/b", "/usr/bin/socat"),
        proxy=shell_sandbox.ProxyEndpoint(unix_path=soket),
    )
    argv = list(plan.prefix)
    assert ["--bind", str(soket.parent), str(soket.parent)] == argv[
        argv.index(str(soket.parent)) - 1 : argv.index(str(soket.parent)) + 2
    ]
    sarmal = argv[argv.index("--") + 3]
    assert f"TCP-LISTEN:{LINUX_BRIDGE_PORT}" in sarmal and f"UNIX-CONNECT:{soket}" in sarmal
    assert sarmal.endswith('exec "$@"')
    assert ("HTTP_PROXY", f"http://127.0.0.1:{LINUX_BRIDGE_PORT}") in plan.env


def test_linux_allowlist_socat_yoksa_kurulamaz(tmp_path):
    policy = SandboxPolicy(network="allowlist", allowed_domains=("pypi.org",))
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=policy,
        platform="linux",
        linux_tools=LinuxTools("/b", None),
        proxy=shell_sandbox.ProxyEndpoint(unix_path=tmp_path / "p.sock"),
    )
    assert plan.prefix == () and "socat" in plan.notice


# --- gerçek sandbox (macOS) ------------------------------------------------- #


@macos_sandbox
def test_okuma_engelli_dizin_okunamaz_diger_okumalar_surer(tmp_path, proje):
    gizli = tmp_path / "ev" / ".ssh"
    gizli.mkdir(parents=True)
    (gizli / "id_rsa").write_text("GIZLI-ANAHTAR")
    (proje / "acik.txt").write_text("acik")
    context = _context(proje, SandboxPolicy(deny_read=(gizli,)))

    engelli = shell.run_shell({"command": f"cat {gizli / 'id_rsa'}"}, context)
    acik = shell.run_shell(
        {"command": "cat acik.txt /etc/hosts > /dev/null && echo tamam"}, context
    )

    assert not engelli.ok and "GIZLI-ANAHTAR" not in engelli.output
    assert "deny_read" in engelli.output
    assert acik.ok and "tamam" in acik.output


@macos_sandbox
def test_ek_yazma_koku_yazilabilir(tmp_path, proje):
    context = _context(proje, SandboxPolicy(extra_write=(tmp_path / "disari",)))
    assert shell.run_shell({"command": "echo b > ../disari/dis.txt"}, context).ok


@macos_sandbox
def test_sir_ortam_degiskeni_sandbox_icinde_gizlenir(proje, monkeypatch):
    monkeypatch.setenv("SAHTE_API_KEY", "sk-sahte-123")
    monkeypatch.setenv("SIRADAN_DEGISKEN", "gorunur")

    gizli = shell.run_shell(
        {"command": "env"}, _context(proje, SandboxPolicy(hide_secret_env=True))
    )
    acik = shell.run_shell({"command": "env"}, _context(proje, SandboxPolicy()))
    ad = shell.run_shell(
        {"command": "env"}, _context(proje, SandboxPolicy(deny_env=("SAHTE_API_KEY",)))
    )

    assert "sk-sahte-123" not in gizli.output and "gorunur" in gizli.output
    # Claude varsayılanı: ortam miras alınır; credentials.envVars adı çıkarır (#368).
    assert "sk-sahte-123" in acik.output
    assert "sk-sahte-123" not in ad.output and "gorunur" in ad.output


def test_sade_rm_kok_disinda_sandbox_acikken_silmez(tmp_path, proje):
    hedef = tmp_path / "disari" / "kalsin.txt"
    hedef.write_text("x")

    sonuc = shell.run_shell({"command": f"rm {hedef}"}, _context(proje))

    assert not sonuc.ok and "Sandbox açık" in sonuc.output
    assert hedef.exists()


def test_fail_if_unavailable_komutu_calistirmaz(proje, monkeypatch):
    monkeypatch.setattr(shell_sandbox.sys, "platform", "win32")
    context = _context(proje, SandboxPolicy(fail_if_unavailable=True))

    sonuc = shell.run_shell({"command": "echo a > olmamali.txt"}, context)

    assert not sonuc.ok and "fail_if_unavailable" in sonuc.output
    assert not (proje / "olmamali.txt").exists()


@macos_sandbox
def test_sandbox_disi_istek_kok_disina_yazar_ve_notu_tasir(tmp_path, proje):
    context = _context(proje)
    sonuc = shell.run_shell({"command": "echo b > ../disari/dis.txt", "unsandboxed": True}, context)
    assert sonuc.ok and (tmp_path / "disari" / "dis.txt").exists()
    assert "sandbox DIŞINDA" in sonuc.output


@macos_sandbox
def test_allow_unsandboxed_kapaliyken_istek_yok_sayilir(tmp_path, proje):
    context = _context(proje, SandboxPolicy(allow_unsandboxed=False))
    sonuc = shell.run_shell({"command": "echo b > ../disari/dis.txt", "unsandboxed": True}, context)
    assert not sonuc.ok and not (tmp_path / "disari" / "dis.txt").exists()
    assert "yok sayıldı" in sonuc.output


# --- onay ------------------------------------------------------------------- #


class _Onayci:
    def __init__(self, cevap: ApprovalAnswer = ApprovalAnswer.ONCE) -> None:
        self.sorulan: list[object] = []
        self._cevap = cevap

    async def confirm(self, request):
        self.sorulan.append(request)
        return self._cevap


def _run_shell():
    return build_registry().get("run_shell")


async def test_sandbox_disi_istek_otomatik_kipte_denetcisizken_sorulur_oturum_izni_ayri(proje):
    """Claude (#351): auto'da sınıflandırıcı karar verir; yoksa sorulur. Oturum izni yalnız
    aynı sandbox dışı komutu kapsar; sandbox'lı komutun izni sandbox dışını kapsamaz."""
    onayci = _Onayci(ApprovalAnswer.SESSION)
    politika = build_policy(ApprovalMode.SECURITY, onayci)
    context = _context(proje, SandboxPolicy(auto_allow=False))
    args = {"command": "touch a.txt", "unsandboxed": True}

    sandboxli = await resolve_request(
        _run_shell(), {"command": "touch a.txt"}, root=proje, context=context
    )
    assert await politika.decide(sandboxli) is Decision.ALLOW  # oturum izni (sandbox içi)
    for _ in range(2):
        istek = await resolve_request(_run_shell(), args, root=proje, context=context)
        assert await politika.decide(istek) is Decision.ALLOW

    assert len(onayci.sorulan) == 2  # sandbox'lı + ilk sandbox dışı; ikincisi oturum izniyle
    assert "sandbox DIŞINDA" in (istek.note or "")
    assert istek.can_remember


async def test_sandbox_disi_allow_kurali_onaylar_ask_ve_deny_kurali_kipten_bagimsiz(proje):
    from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule

    def kurallar(*pairs):
        return PermissionRuleSet(
            tuple(parse_rule(text, decision, source="test") for text, decision in pairs)
        )

    context = _context(proje)
    args = {"command": "npm test", "unsandboxed": True}
    izin = await resolve_request(
        _run_shell(),
        args,
        root=proje,
        context=context,
        rules=kurallar(("Bash(npm test)", PermissionDecision.ALLOW)),
    )
    assert izin.pre_allowed
    onayci = _Onayci()
    assert await build_policy(ApprovalMode.DONT_ASK, onayci).decide(izin) is Decision.ALLOW

    sor = await resolve_request(
        _run_shell(),
        args,
        root=proje,
        context=context,
        rules=kurallar(
            ("Bash(npm test)", PermissionDecision.ALLOW),
            ("Bash(dangerouslyDisableSandbox:true)", PermissionDecision.ASK),
        ),
    )
    assert sor.pre_ask is not None and not sor.pre_allowed
    assert await build_policy(ApprovalMode.BYPASS, onayci).decide(sor) is not Decision.BLOCKED

    yasak = await resolve_request(
        _run_shell(),
        args,
        root=proje,
        context=context,
        rules=kurallar(("Bash(dangerouslyDisableSandbox:true)", PermissionDecision.DENY)),
    )
    assert yasak.pre_denied is not None


async def test_sandbox_kapaliyken_unsandboxed_arguman_onayi_degistirmez(proje):
    context = ToolContext(root=proje)
    istek = await resolve_request(
        _run_shell(), {"command": "ls", "unsandboxed": True}, root=proje, context=context
    )
    assert istek.pre_ask is None


async def test_auto_allow_ag_allowlist_teyken_manuel_kipte_sormaz(proje):
    onayci = _Onayci()
    politika = build_policy(ApprovalMode.SECURITY, onayci)
    policy = SandboxPolicy(auto_allow=True, network="allowlist")
    istek = await resolve_request(
        _run_shell(), {"command": "touch yeni.txt"}, root=proje, context=_context(proje, policy)
    )
    assert await politika.decide(istek) is Decision.ALLOW
    assert onayci.sorulan == [] and "autoAllowBashIfSandboxed" in (istek.note or "")


async def test_auto_allow_ag_kipinden_bagimsiz_yikicida_ve_atamada_yine_sorar(proje):
    """Claude (#347): ağ şartı yok; yıkıcı ve `FOO=bar cmd` biçimi olağan akıştan geçer."""
    onayci = _Onayci()
    politika = build_policy(ApprovalMode.SECURITY, onayci)
    acik_ag = await resolve_request(
        _run_shell(),
        {"command": "touch yeni.txt"},
        root=proje,
        context=_context(proje, SandboxPolicy(auto_allow=True, network="open")),
    )
    assert acik_ag.pre_allowed
    atama = await resolve_request(
        _run_shell(),
        {"command": "FOO=bar touch yeni.txt"},
        root=proje,
        context=_context(proje, SandboxPolicy(auto_allow=True)),
    )
    yikici = await resolve_request(
        _run_shell(),
        {"command": "git push --force origin main"},
        root=proje,
        context=_context(proje, SandboxPolicy(auto_allow=True, network="allowlist")),
    )
    await politika.decide(atama)
    await politika.decide(yikici)
    assert len(onayci.sorulan) == 2


async def test_plan_kipi_auto_allow_ile_de_yazma_komutunu_sorar(proje):
    """Claude (#52): plan kipinde okuma dışı komut sandbox auto-allow açık olsa da sorulur."""
    onayci = _Onayci()
    politika = build_policy(ApprovalMode.PLAN, onayci)
    policy = SandboxPolicy(auto_allow=True, network="allowlist")
    istek = await resolve_request(
        _run_shell(), {"command": "touch yeni.txt"}, root=proje, context=_context(proje, policy)
    )
    await politika.decide(istek)
    assert len(onayci.sorulan) == 1


async def test_kurulamayan_sandbox_fail_if_unavailable_ile_sorulmadan_engellenir(
    proje, monkeypatch
):
    monkeypatch.setattr(shell_sandbox.sys, "platform", "win32")
    onayci = _Onayci()
    istek = await resolve_request(
        _run_shell(),
        {"command": "ls"},
        root=proje,
        context=_context(proje, SandboxPolicy(fail_if_unavailable=True)),
    )
    assert await build_policy(ApprovalMode.AUTO, onayci).decide(istek) is Decision.BLOCKED
    assert onayci.sorulan == []


async def test_sandbox_disi_listedeki_komut_kartta_belirtilir(proje):
    policy = SandboxPolicy(excluded_commands=("docker",))
    istek = await resolve_request(
        _run_shell(), {"command": "docker ps"}, root=proje, context=_context(proje, policy)
    )
    assert istek.pre_ask is None and "excluded_commands" in (istek.note or "")


# --- yapılandırma ----------------------------------------------------------- #


def test_defaults_yaml_sandbox_bolumu_dataclass_varsayilaniyla_ayni():
    defaults = yaml.safe_load(bundled_defaults().read_text(encoding="utf-8"))["sandbox"]
    beklenen = SandboxConfig()
    for name, value in defaults.items():
        gercek = getattr(beklenen, name)
        assert (list(gercek) if isinstance(gercek, tuple) else gercek) == value, name
    assert set(defaults) == set(SandboxConfig.__slots__)


def test_eski_yapilandirma_sandbox_bolumsuz_yuklenir(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  shell_sandbox: write_root\n")
    config = load_config(yol)
    assert config.runtime.shell_sandbox == "write_root"
    assert config.sandbox == SandboxConfig()


def test_gecersiz_alan_adi_ve_ag_kipi_reddedilir(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("sandbox:\n  allowed_domains: ['http://kotu']\n")
    with pytest.raises(ConfigError, match="allowed_domains"):
        load_config(yol)
    yol.write_text("sandbox:\n  network: kapali\n")
    with pytest.raises(ConfigError, match=r"sandbox\.network"):
        load_config(yol)


def test_guvenilmeyen_proje_sandbox_bolumunu_gevsetemez():
    temiz, dusen = trust.without_execution_settings(
        {"sandbox": {"auto_allow": True, "excluded_commands": ["sh"]}}
    )
    assert "sandbox" not in temiz and "sandbox" in dusen


def test_politika_tildeyi_ve_goreli_yolu_cozer_fusion_sirlarini_ekler(tmp_path):
    ev, kok = tmp_path / "ev", tmp_path / "kok"
    config = SandboxConfig(allow_write=("~/.npm", "build"), deny_read=("gizli",))
    policy = sandbox_policy(config, home=ev, root=kok, extra_deny=(tmp_path / "kasa",))
    assert policy.extra_write == (ev / ".npm", kok / "build")
    assert policy.deny_read == (kok / "gizli", tmp_path / "kasa")  # yerleşik liste yok (#348)
    assert policy.locked_read == (tmp_path / "kasa",)


def test_config_yolu_sandbox_alan_adlarini_kanonik_yazar(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  shell_sandbox: write_root\n")
    config = load_config(yol)
    guncel, hedef = write_setting(config, "sandbox.allowed_domains", "GitHub.com, *.npmjs.org", yol)
    assert guncel.sandbox.allowed_domains == ("github.com", "*.npmjs.org")
    assert yaml.safe_load(hedef.read_text())["sandbox"]["allowed_domains"] == [
        "github.com",
        "*.npmjs.org",
    ]
    assert read_setting(guncel, "sandbox.network") == "allowlist"  # Claude varsayılanı (#323)
    with pytest.raises(ConfigError, match="geçerli bir alan adı"):
        apply_setting(config, "sandbox.allowed_domains", "a b")
    with pytest.raises(ConfigError, match="İzin verilen"):
        apply_setting(config, "runtime.shell_sandbox", "tam")


def test_validate_bos_onek_reddedilir():
    with pytest.raises(ConfigError, match="excluded_commands"):
        validate_sandbox(SandboxConfig(excluded_commands=(" ",)))


def test_politikasiz_baglam_varsayilani_da_proxyli_izin_listesi():
    """Claude: sandbox açıkken ağ her zaman proxy'den geçer (#323). Politikası doldurulmamış
    bağlamın yedeği (`SandboxPolicy()`) de açık ağ değil (bağımsız inceleme #11)."""
    from fusion_cli.config.sandbox_config import SandboxConfig

    assert SandboxPolicy().restricts_network
    assert SandboxPolicy().network == SandboxConfig().network
