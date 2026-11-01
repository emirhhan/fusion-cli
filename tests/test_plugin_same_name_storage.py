"""Aynı adlı iki kurulumun veri klasörü, userConfig değerleri ve sırları ayrıdır (#391, #408).

Claude Code: `${CLAUDE_PLUGIN_DATA}` eklenti KİMLİĞİYLE (`ad@pazar`) anahtarlanır; kaldırma
yalnız o kurulumun verisini, ayarını ve sırlarını siler. Eski sürümün yalnız adla yazdığı
veri, o adı ilk alan kurulumun kimliğine bir kez taşınır.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.config import plugin_store, plugin_user_config
from fusion_cli.config.plugin_data import plugin_data_dir
from fusion_cli.config.plugin_storage import storage_key, storage_key_for_root
from fusion_cli.config.plugin_user_config import UserOption
from fusion_cli.tools import plugin_install

from .test_plugin_same_name import _market

_SCHEMA = (
    UserOption("api_url", "string", "API", "Adres"),
    UserOption("api_token", "string", "Token", "T", sensitive=True),
)


@pytest.fixture(autouse=True)
def _vault_key(monkeypatch):
    monkeypatch.setenv("FUSION_SECRET_KEY", "test-yalniz-eklenti-anahtari")


def _iki_kurulum(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path, "ekip")))
    plugin_install.add_marketplace(str(_market(tmp_path, "baska")))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    plugin_install.install_plugin("rapor@baska", approve=lambda _p: True)
    state = plugin_store.load_state()
    return state.plugin("rapor@ekip"), state.plugin("rapor@baska")


def test_iki_kurulumun_depolama_anahtari_ayri(tmp_path):
    ekip, baska = _iki_kurulum(tmp_path)

    assert storage_key(ekip) == "rapor@ekip"
    assert storage_key(baska) == "rapor@baska"
    base = plugin_store.plugins_dir()
    assert storage_key_for_root(plugin_store.plugin_folder(ekip, base), "rapor") == "rapor@ekip"
    assert storage_key_for_root(plugin_store.plugin_folder(baska, base), "rapor") == "rapor@baska"


def test_birini_kaldirmak_otekinin_verisini_ayarini_sirlarini_silmez(tmp_path):
    ekip, baska = _iki_kurulum(tmp_path)
    base = plugin_store.plugins_dir()
    for record, url in ((ekip, "https://ekip"), (baska, "https://baska")):
        folder = plugin_data_dir(storage_key(record), create=True)
        (folder / "veri.txt").write_text(url, "utf-8")
        values = {"api_url": url, "api_token": f"gizli-{url}"}
        plugin_user_config.save_values(storage_key(record), _SCHEMA, values, base)

    plugin_install.uninstall_plugin("rapor@baska")

    kalan = plugin_data_dir("rapor@ekip") / "veri.txt"
    assert kalan.read_text("utf-8") == "https://ekip"
    assert not plugin_data_dir("rapor@baska").exists()
    saved = plugin_user_config.saved_values("rapor@ekip", base)
    assert saved == {"api_url": "https://ekip", "api_token": "gizli-https://ekip"}
    assert plugin_user_config.saved_values("rapor@baska", base) == {}


def test_eski_ad_anahtarli_veri_ilk_kurulumun_kimligine_tasinir(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path, "ekip")))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    base = plugin_store.plugins_dir()
    # Eski sürüm: veri, ayar ve mcpb paket ayarı yalnız adla; kayıt sürümü 2.
    eski = plugin_data_dir("rapor", create=True)
    (eski / "veri.txt").write_text("eski", "utf-8")
    plugin_user_config.save_values("rapor", _SCHEMA, {"api_url": "https://eski"}, base)
    plugin_user_config.save_values("rapor/srv", _SCHEMA, {"api_url": "https://paket"}, base)
    path = plugin_store.state_file()
    raw = json.loads(path.read_text("utf-8"))
    path.write_text(json.dumps({**raw, "surum": 2}), "utf-8")

    plugin_store.installed_plugins()

    assert (plugin_data_dir("rapor@ekip") / "veri.txt").read_text("utf-8") == "eski"
    assert not eski.exists()
    assert plugin_user_config.saved_values("rapor@ekip", base) == {"api_url": "https://eski"}
    assert plugin_user_config.saved_values("rapor@ekip/srv", base) == {"api_url": "https://paket"}
    assert plugin_user_config.saved_values("rapor", base) == {}
