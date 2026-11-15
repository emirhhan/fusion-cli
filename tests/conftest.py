"""Tüm testler için ortak izolasyon.

Testler geliştiricinin KİŞİSEL yapılandırmasını okumamalı. `load_config()`
`~/.config/fusion-cli/config.yaml` dosyasını buluyordu; testler o makinedeki
ayara göre geçip kalıyordu.

Ölçüldü (2026-07-26): kişisel config'e `provider: nvidia` yazılınca dört test
kırıldı — kod hiç değişmemişti. Bu, testlerin yalan söylemesinin en sinsi
biçimidir: CI'da yeşil, geliştiricide kırmızı (ya da tersi).
"""

from __future__ import annotations

import gc
import os
import sys
from pathlib import Path

import pytest

#: Testlerin ASLA değiştirmemesi gereken gerçek kullanıcı dizinleri (kasa anahtarı, eşleşmiş
#: telefonlar). Ölçüldü (30 Ekim): `tests/` dışındaki gizli kabul testini koşan bir test
#: HOME vermeden alt süreç açtı; `load_config` geliştiricinin gerçek `master.key`'ini
#: Keychain'e taşıyıp `master.key.migrated` yaptı. Oturum sonunda değişiklik varsa koşu düşer.
_KORUNAN_DIZINLER = (
    Path.home() / ".local" / "share" / "fusion-cli" / "vault",
    Path.home() / "remote",
)


def _dizin_izi() -> tuple[tuple[str, int, int], ...]:
    iz: list[tuple[str, int, int]] = []
    for dizin in _KORUNAN_DIZINLER:
        try:
            ogeler = sorted(dizin.iterdir())
        except OSError:
            continue
        for oge in ogeler:
            try:
                bilgi = oge.stat()
            except OSError:
                continue
            iz.append((str(oge), bilgi.st_size, bilgi.st_mtime_ns))
    return tuple(iz)


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_IZ_ANAHTARI] = _dizin_izi()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # xdist işçileri değil yalnız denetleyici süreç karşılaştırır.
    if hasattr(session.config, "workerinput"):
        return
    once = session.config.stash.get(_IZ_ANAHTARI, None)
    if once is None or once == _dizin_izi():
        return
    session.config.get_terminal_writer().line(
        "UYARI: testler gerçek kullanıcı dizinini değiştirdi: "
        + ", ".join(str(d) for d in _KORUNAN_DIZINLER),
        red=True,
        bold=True,
    )
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


_IZ_ANAHTARI = pytest.StashKey[tuple[tuple[str, int, int], ...]]()


@pytest.fixture(autouse=True)
def test_yorumlayicisi_pathte(monkeypatch):
    """Kabukta koşan test komutları (`python`, `pytest`) testi koşan ortamı bulsun.

    Ölçüldü (11 Ekim, yeni Mac): genel `python`/`pytest` kurulu olmayan makinede
    iki test "command not found" ile düştü — kod değişmemişti, eski makinede bu
    komutlar sistem genelinde vardı. Test sonucu makinenin PATH'ine bağlı olmamalı.
    """
    venv_bin = str(Path(sys.executable).parent)
    monkeypatch.setenv("PATH", venv_bin + os.pathsep + os.environ.get("PATH", ""))


@pytest.fixture(autouse=True)
def ortam_sizintisini_geri_al(monkeypatch):
    """Her test aynı süreç ortamıyla başlasın ve bitsin.

    Üretim kodu sırları `os.environ`'a doğrudan yazıyor (`.env` yükleme, sır
    deposu, gateway). `monkeypatch` bunları geri almaz. Ölçüldü (30 Eylül): bir
    testin bıraktığı `OPENROUTER_API_KEY` sonraki `load_config()`'i NIM'siz
    budatıp `test_keys` testini yalnız tam koşuda düşürüyordu.

    Geliştiricinin kabuğundaki gerçek anahtarlar da testlere girmez: aksi hâlde
    test anahtarlı makinede geçer, CI'da düşerdi.
    """
    from fusion_cli.config import keys

    for degisken in (keys.OPENROUTER_ENV, keys.NIM_ENV):
        monkeypatch.delenv(degisken, raising=False)
    onceki = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(onceki)


@pytest.fixture
def yazma_yasagi_kurulabilir():
    """`chmod` ile yazma yasağı kurulabilen ortam şartı.

    root dosya izinlerini yok sayar (bulut kapsayıcıları root çalışır); orada
    "yazılamayan dosya" senaryosu kurulamaz ve test yanlış yere işaret ederdi.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root dosya izinlerini yok sayar; yazma yasağı kurulamaz")


@pytest.fixture(autouse=True)
def izole_kalici_bellek():
    """Testler arasında Chroma istemcilerinin dosya tanıtıcılarını bırak."""
    yield

    from fusion_cli.memory.store import reset_clients

    reset_clients()
    gc.collect()


@pytest.fixture(autouse=True)
def izole_kullanici_yapilandirmasi(monkeypatch, tmp_path):
    """Yalnızca pakete gömülü `defaults.yaml` kullanılsın.

    Ortam değişkenleriyle gelen override'lar da temizlenir: geliştiricinin
    kabuğunda `FUSION_CONFIG` tanımlıysa testler onu okurdu.
    """
    from fusion_cli.config import loader

    monkeypatch.setattr(loader, "user_config_candidates", tuple)
    for degisken in ("FUSION_CONFIG", "FUSION_HOME"):
        monkeypatch.delenv(degisken, raising=False)
    # AppSession konuşma dökümünü kalıcı belleğe yazar. Test turları gerçek
    # ~/.local/share/fusion-cli/memory geçmişine karışmamalıdır.
    # Keep the persistent-memory fixture outside the workspace root. Appserver
    # workspace tests intentionally inspect the complete project tree; placing
    # Chroma's files below ``tmp_path`` makes that host-only test dependency
    # look like user project content and also pollutes Git status.
    monkeypatch.setenv(
        "FUSION_MEMORY_DIR",
        str(tmp_path.parent / f".{tmp_path.name}-fusion-memory"),
    )
    # Web profilleri ve paylaşılan Chrome kiraları kullanıcı veri dizininde durur.
    # Havuzu kapatan bir test gerçek dizine giderse kullanıcının AÇIK Fusion
    # Chrome'unu kapatabilirdi.
    user_data = tmp_path.parent / f".{tmp_path.name}-fusion-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(user_data))
    monkeypatch.setenv("LOCALAPPDATA", str(user_data))
    # Chrome köprüsü açılınca eşleşme dosyası yapılandırma köküne yazılır ve
    # Chrome'a yerel mesajlaşma sunucusu tanıtılır; testler gerçek dizinlere dokunmaz.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path.parent / f".{tmp_path.name}-fusion-config"))
    monkeypatch.setenv("FUSION_NO_NATIVE_HOST", "1")
    # Kurumsal Claude Code dizini (`/Library/Application Support/ClaudeCode`) okunmasın.
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(tmp_path.parent / f".{tmp_path.name}-mg"))
    # Otomatik bellek `~/.claude/projects/<proje>/memory` (#153): testler gerçek eve yazmasın.
    monkeypatch.setenv("FUSION_CLAUDE_HOME", str(tmp_path.parent / f".{tmp_path.name}-claude-ev"))
    # Kullanıcı izin kuralları artık Claude gibi `~/.claude/settings.json`'a yazılır (#66):
    # HOME'u yalıtmayan bir test gerçek ayar dosyasına kural eklemesin (ölçüldü, 1 Kasım).
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        # Playwright tarayıcı ikilileri gerçek ev dizinindeki önbellekte durur (salt okunur).
        cache = Path.home() / "Library" / "Caches" / "ms-playwright"
        if not cache.is_dir():
            cache = Path.home() / ".cache" / "ms-playwright"
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    ev = tmp_path.parent / f".{tmp_path.name}-home"
    ev.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(ev))
    # Claude yönetilen ayarları (#65) gerçek sistem dizininden okunmasın.
    monkeypatch.setenv(
        "FUSION_CLAUDE_MANAGED_DIR", str(tmp_path.parent / f".{tmp_path.name}-managed")
    )
    # Computer use bildirimi (#447) testte gerçek macOS bildirimi göstermesin.
    monkeypatch.setenv("FUSION_NO_OS_NOTIFY", "1")
    # Geliştiricinin gerçek `~/.claude/settings.json` değerleri (defaultMode, worktree.baseRef,
    # bashOutputMaxChars…) testlere sızmasın (Claude Code `CLAUDE_CONFIG_DIR`).
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path.parent / f".{tmp_path.name}-claude"))
    # Geliştiricinin `~/.claude/settings.json` kancaları (P-009) test turlarında çalışmasın;
    # kanca testleri bu değişkeni kendileri kaldırır.
    monkeypatch.setenv("FUSION_HOOKS", "off")


@pytest.fixture(autouse=True)
def izole_sistem_anahtarligi(monkeypatch):
    """Hiçbir test gerçek sistem anahtarlığına (macOS Keychain vb.) dokunmasın.

    `GatewayApp` store verilmeden kurulunca `_default_secret_store` → `secret_key`
    → `_keyring_master_key` gerçek keychain'e gidip master key'i YAZMAYA çalışıyordu.
    Bu, geliştiricinin login keychain'ine yan etki bırakıyor ve GUI olmayan süreçte
    "saklanacağı anahtar zinciri bulunamadı" hatasını kullanıcının ekranına düşürüyordu.
    Anahtarı açıkça veren testler (`FernetSecretStore(secret_key=...)`) etkilenmez.
    """
    from fusion_cli.config import keys

    monkeypatch.setattr(keys, "_keyring_master_key", lambda: None)
    monkeypatch.setattr(keys, "_local_master_key", lambda: None)
    monkeypatch.delenv(keys.FUSION_SECRET_ENV, raising=False)
    # `local_vault.local_master_key` doğrudan çağıran testler de gerçek Keychain'e
    # gitmesin (L2-27): sistem arka ucu kapalı, sahte arka uç testte enjekte edilir.
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")


@pytest.fixture(autouse=True)
def izole_web_aramasi(monkeypatch):
    """Hiçbir test gerçek arama motoruna çıkmasın.

    Dış platform kontrolü (`platform_check`) istekte "Instagram", "Shopify" gibi
    bir ad geçince `web_search` çalıştırır. Bu adları içeren eski testler aksi
    halde ağa bağımlı, yavaş ve kararsız olurdu. Aramayı sınayan testler kendi
    sahte uç noktalarını `monkeypatch` ile verir.
    """
    from fusion_cli.tools import web

    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (lambda _query: [],))


@pytest.fixture(autouse=True)
def _yerlesik_beceriler_yalitilir(tmp_path_factory, monkeypatch):
    """Pakete gömülü beceriler keşif testlerinin beklediği listeye karışmasın.

    Yerleşik beceriyi ölçen test bu yamayı kendi içinde geri alır.
    """
    bos = tmp_path_factory.mktemp("yerlesik-beceri-yok")
    monkeypatch.setattr("fusion_cli.tools.capabilities.bundled_skills_dir", lambda: bos)


@pytest.fixture(autouse=True)
def _codex_hazir_degil(monkeypatch: pytest.MonkeyPatch) -> None:
    """Testler makinedeki gerçek Codex girişine bağlı olmasın: öğretmen yedeği eklenmez."""
    monkeypatch.setattr("fusion_cli.providers.codex_cli.codex_ready", lambda: False)


@pytest.fixture(autouse=True)
def godot_kesfi_makineden_bagimsiz(monkeypatch):
    """Kapı komutları makinede kurulu Godot'a bağlı olmasın (E1-10).

    `GODOT_BIN` temizlenir ve uygulama paketi aranmaz; keşfi sınayan testler
    `monkeypatch` ile kendi ortamını kurar.
    """
    from fusion_cli.engines.agent.domain_adapters import godot

    monkeypatch.delenv("GODOT_BIN", raising=False)
    monkeypatch.setattr(godot, "GODOT_APP_BUNDLES", ())


@pytest.fixture(autouse=True)
def _mcp_etkilesimsiz_kip_sizmaz():
    """`fusion agent` (Claude `-p`) süreç genelinde etkileşimsiz MCP kipini açar ve kapatmaz.

    Ölçüldü (2 Kasım): CliRunner ile `agent` çağıran bir test bu işareti açık bırakınca aynı
    xdist işçisindeki MCP havuzu testi sunucuyu sonsuza dek bekliyor, tam paket asılıyordu.
    """
    from fusion_cli.config import mcp_project_approval

    mcp_project_approval.set_noninteractive(False)
    yield
    mcp_project_approval.set_noninteractive(False)


@pytest.fixture(autouse=True)
def _fusion_gunluk_isleyicisi_sizmaz():
    """`main()` çağıran testin bağladığı `logs/fusion.log` işleyicisi sonraki teste kalmasın.

    Ölçüldü (31 Ekim, tam paralel koşu): CLI `main()`'i çağıran bir test `fusion_cli`
    günlüğüne GERÇEK veri dizinindeki dosyayı gösteren işleyici bırakıyordu; aynı süreçteki
    günlük sızıntısı testi "işleyici zaten var" deyip kendi geçici dosyasını kurmuyordu.
    """
    import logging

    kok = logging.getLogger("fusion_cli")
    onceki = list(kok.handlers)
    yield
    for handler in [h for h in kok.handlers if h not in onceki]:
        if getattr(handler, "_fusion_dosya", False):
            kok.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def izole_oturum_izin_kurallari():
    """`fusion agent --allowedTools/--disallowedTools` süreç kuralları testten teste taşınmasın."""
    from fusion_cli.config.permission_rules import set_session_rules

    set_session_rules(())
    yield
    set_session_rules(())


@pytest.fixture
def guvenilir_klasor(monkeypatch):
    """Etkileşimli kanca testleri: klasör güveni verilmiş sayılır (#108 kapısı ayrı sınanır)."""
    from fusion_cli.config import hook_trust

    monkeypatch.setattr(hook_trust, "is_workspace_trusted", lambda root: True)


@pytest.fixture(autouse=True)
def _eklenti_ayar_dosyalari_yalitilir(monkeypatch, tmp_path):
    """Eklenti `enabledPlugins`/`extraKnownMarketplaces` user ve managed katmanları (#376)
    gerçek `~/.claude/settings.json` ve kuruluş `managed-settings.json`'ına dokunmasın."""
    from fusion_cli.config import plugin_scopes

    ayar = tmp_path.parent / f".{tmp_path.name}-claude-ayar"
    monkeypatch.setattr(plugin_scopes, "user_settings_file", lambda: ayar / "settings.json")
    monkeypatch.setattr(
        plugin_scopes, "managed_settings_file", lambda: ayar / "managed-settings.json"
    )


@pytest.fixture(autouse=True)
def izole_yonetilen_ayarlar(monkeypatch):
    """Testler sistemdeki Claude managed-settings dizinini okumasın (#321)."""
    from fusion_cli.config import claude_top_layers

    monkeypatch.setattr(claude_top_layers, "MANAGED_DIRS", {})


@pytest.fixture(autouse=True)
def git_ortamini_temizle(monkeypatch):
    """Test depoları (`git init` + `git config user.name "Fusion Test"`) gerçek depoya yazmasın.

    Ölçüldü (1 Kasım): `GIT_DIR`/`GIT_WORK_TREE` ortamdan miras kalınca (git kancası, başka
    çalışma ağacından başlatılan koşu) geçici dizindeki `git init` ve `git config` ana deponun
    `.git/config`'ine `user.name = Fusion Test` ve `core.worktree` yazmıştı.
    """
    for degisken in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
    ):
        monkeypatch.delenv(degisken, raising=False)


@pytest.fixture
def public_example_dns(monkeypatch):
    """Politika/batch birim testindeki example.com genel adresi ağsız çözülür."""
    import socket

    def lookup(host, port, *_args, **_kwargs):
        assert host == "example.com", "Bu fixture yalnız sentetik example.com hedefini çözer"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
