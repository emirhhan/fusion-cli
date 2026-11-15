"""Native host yalnız gerçek Fusion Browser eklentisine açılır (WP09).

Ölçüldü (29 Ekim): Chrome profilinde ADI "Fusion Browser" olan ya da yolu
`/chrome-extension` ile biten HERHANGİ bir eklenti yerel mesajlaşma izin listesine
ekleniyordu. Aynı adı taşıyan bir eklenti native host'a bağlanıp köprü belirtecini
alabilir ve ajanın tarayıcı köprüsünü sürebilirdi. Gerçek eklentinin manifest
`key`'i kimliği sabitler; ad ve yol soneki kimlik kanıtı değildir.
"""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.appserver import chrome_host


def _profil(tmp_path: Path, uzantilar: dict[str, dict[str, object]]) -> None:
    profil = tmp_path / "Library/Application Support/Google/Chrome/Default"
    profil.mkdir(parents=True)
    (profil / "Preferences").write_text(
        json.dumps({"extensions": {"settings": uzantilar}}), encoding="utf-8"
    )


def test_sahte_adli_ve_sahte_yollu_eklenti_kabul_edilmez(tmp_path):
    _profil(
        tmp_path,
        {
            "sahte1": {"manifest": {"name": "Fusion Browser"}, "path": "/tmp/kotu"},
            "sahte2": {"manifest": {"name": "X"}, "path": "/Users/x/Downloads/chrome-extension"},
        },
    )

    kimlikler = chrome_host.candidate_extension_ids(tmp_path)

    assert "sahte1" not in kimlikler and "sahte2" not in kimlikler
    assert chrome_host.FIXED_EXTENSION_ID in kimlikler


def test_guvenilir_klasorden_yuklenen_eklenti_kabul_edilir(tmp_path):
    guvenilir = chrome_host.trusted_extension_dirs()[0]
    _profil(tmp_path, {"gercek": {"manifest": {"name": "Fusion Browser"}, "path": str(guvenilir)}})

    assert "gercek" in chrome_host.candidate_extension_ids(tmp_path)


def test_native_host_bildirimi_yalniz_guvenilir_kimlikleri_listeler(tmp_path, monkeypatch):
    monkeypatch.delenv("FUSION_NO_NATIVE_HOST", raising=False)
    monkeypatch.setattr(chrome_host.sys, "platform", "darwin")
    _profil(tmp_path, {"sahte": {"manifest": {"name": "Fusion Browser"}, "path": "/tmp/kotu"}})

    yazilan = chrome_host.install_native_host(
        chrome_host.candidate_extension_ids(tmp_path), tmp_path
    )

    bildirim = json.loads(
        next(p for p in yazilan if p.suffix == ".json").read_text(encoding="utf-8")
    )
    assert "chrome-extension://sahte/" not in bildirim["allowed_origins"]
