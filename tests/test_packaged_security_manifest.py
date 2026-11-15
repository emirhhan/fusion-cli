"""Masaüstü kabuğunun güvenlik ayarları geri gevşetilmez (R2-04, WP18).

Ölçüldü (28 Ekim): CSP yalnız `frame-src` içeriyordu ve `asset://` kapsamı bütün
`$HOME`'du. Arayüzde bir XSS, `fetch("asset://…/.ssh/id_rsa")` ile dosyayı okuyup
herhangi bir adrese gönderebilirdi. Arayüz JavaScript'ten hiç ağ isteği yapmaz
(her şey Tauri IPC'si); `connect-src` yalnız IPC'ye izin verince dosya içeriği okunamaz.
Hassas klasörler ayrıca asset kapsamından yasaklanır (yasak, izinden önce gelir).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_CONF = Path(__file__).resolve().parents[1] / "app" / "src-tauri" / "tauri.conf.json"


def _security() -> dict:
    return json.loads(_CONF.read_text(encoding="utf-8"))["app"]["security"]


def test_uretim_csp_ag_istegini_yalniz_ipcye_acar():
    csp = _security()["csp"]

    assert isinstance(csp, dict), "CSP yönerge sözlüğü olmalı (yalnız frame-src değil)"
    assert csp["default-src"] == "'self'"
    assert set(csp["connect-src"].split()) == {"ipc:", "http://ipc.localhost"}
    assert "'unsafe-inline'" not in csp["script-src"] and "'unsafe-eval'" not in csp["script-src"]
    assert csp["object-src"] == "'none'"


@pytest.mark.parametrize(
    "yasak",
    ["$HOME/.ssh/**", "$HOME/.aws/**", "$HOME/**/.env", "$HOME/**/secrets.enc",
     "$HOME/Library/Application Support/Google/Chrome/**",
     "$HOME/.local/share/fusion-cli/vault/**"],
)  # fmt: skip
def test_hassas_klasorler_asset_kapsamindan_yasaktir(yasak):
    scope = _security()["assetProtocol"]["scope"]

    assert yasak in scope["deny"]


# Q1-08 — Ölçüldü (30 Ekim): kapsamın `$HOME/**` izni, yasak listesinde olmayan her yerel görseli
# (Masaüstü, Belgeler, Fotoğraflar…) `asset://` üzerinden açıyordu. Statik izinler yalnız
# Fusion'ın ürettiği klasörlerdir; proje kökleri çalışma anında `session_manager.rs` ile eklenir.
_GENIS_IZINLER = {"$HOME/**", "$HOME/*", "$HOME", "$HOME/", "/**", "**", "$LOCALDATA/**"}


def test_asset_kapsami_butun_ev_dizinine_acik_degildir():
    allow = _security()["assetProtocol"]["scope"]["allow"]

    assert not _GENIS_IZINLER & set(allow), allow
    izinli_onekler = ("$HOME/.local/share/fusion-cli/", "$HOME/.config/fusion-cli/")
    izinli_onekler += ("$HOME/remote/uploads/", "$LOCALDATA/fusion-cli/gallery/")
    assert all(item.startswith(izinli_onekler) for item in allow), allow


@pytest.mark.parametrize(
    "gerekli",
    [
        "$HOME/.local/share/fusion-cli/gallery/**",
        "$HOME/.local/share/fusion-cli/library/yuklenenler/**",
        "$HOME/remote/uploads/**",
        "$HOME/.config/fusion-cli/accounts/*/avatar.*",
        "$LOCALDATA/fusion-cli/gallery/**",
    ],
)
def test_fusionin_urettigi_klasorler_asset_kapsaminda_kalir(gerekli):
    assert gerekli in _security()["assetProtocol"]["scope"]["allow"]
