from __future__ import annotations

import io
import json
import os
import struct
from pathlib import Path

from fusion_cli.appserver import chrome_host


def _ileti(veri: dict) -> io.BytesIO:
    govde = json.dumps(veri).encode()
    return io.BytesIO(struct.pack("<I", len(govde)) + govde)


def _cevap(akis: io.BytesIO) -> dict:
    ham = akis.getvalue()
    (uzunluk,) = struct.unpack("<I", ham[:4])
    return json.loads(ham[4 : 4 + uzunluk])


def test_kopru_calisirken_eslesme_bilgisi_verilir_ve_dosya_yalniz_kullaniciya_acik():
    chrome_host.write_bridge_state(51234, "gizli")
    cikti = io.BytesIO()

    chrome_host.serve(_ileti({"type": "pair"}), cikti)

    assert _cevap(cikti) == {"ok": True, "port": 51234, "anahtar": "gizli"}
    assert oct(chrome_host.bridge_state_file().stat().st_mode & 0o777) == "0o600"


def test_sahibi_olmus_ya_da_silinmis_kopru_bildirilmez():
    chrome_host.write_bridge_state(51234, "gizli", pid=999_999)
    cikti = io.BytesIO()
    chrome_host.serve(_ileti({"type": "pair"}), cikti)
    assert _cevap(cikti)["ok"] is False

    chrome_host.write_bridge_state(1, "x", pid=1)
    chrome_host.clear_bridge_state()  # başka sürecin (pid 1) kaydı silinmez
    assert chrome_host.bridge_state_file().exists()
    chrome_host.write_bridge_state(1, "x", pid=os.getpid())
    chrome_host.clear_bridge_state()
    assert not chrome_host.bridge_state_file().exists()


def test_eklenti_kimligi_chrome_yontemiyle_hesaplanir():
    # Chrome: yolun SHA-256 özetinin ilk 32 onaltılık hanesi, 0-f → a-p.
    yol = Path("/Users/kullanici/Desktop/01-Projeler/fusion-cli/chrome-extension")
    assert chrome_host.extension_id_for_path(yol) == "eigpikpghdhbbefejciokiinjcpiegjc"


def test_yuklu_fusion_browser_kimligi_yalniz_guvenilir_klasorden_bulunur(tmp_path):
    """Ad kimlik kanıtı değildir (bkz. test_native_host_identity)."""
    profil = tmp_path / "Library/Application Support/Google/Chrome/Default"
    profil.mkdir(parents=True)
    guvenilir = str(chrome_host.trusted_extension_dirs()[0])
    (profil / "Preferences").write_text(
        json.dumps(
            {
                "extensions": {
                    "settings": {
                        "abc": {"manifest": {"name": "Fusion Browser"}, "path": guvenilir},
                        "adi-ayni": {"manifest": {"name": "Fusion Browser"}, "path": "/tmp/x"},
                        "xyz": {"manifest": {"name": "Başka"}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert chrome_host.installed_extension_ids(tmp_path) == {"abc"}


def test_bilinmeyen_istek_reddedilir():
    cikti = io.BytesIO()
    chrome_host.serve(_ileti({"type": "başka"}), cikti)
    assert _cevap(cikti)["ok"] is False


def test_bozuk_json_govdesi_sureci_cokertmez():
    """Ölçüldü (30 Ekim, S1-53): geçersiz JSON `ValueError` ile host sürecini çökertiyordu."""
    govde = b"{bozuk"
    akis = io.BytesIO(struct.pack("<I", len(govde)) + govde)
    cikti = io.BytesIO()

    chrome_host.serve(akis, cikti)

    assert cikti.getvalue() == b""


def test_mevcut_gevsek_izinli_durum_dosyasi_yeniden_yazilirken_sikilasir():
    """Ölçüldü (30 Ekim, S1-53): `os.open` modu yalnız oluşturmada uygulanıyordu."""
    yol = chrome_host.bridge_state_file()
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("{}", encoding="utf-8")
    yol.chmod(0o644)

    chrome_host.write_bridge_state(1234, "gizli")

    assert oct(yol.stat().st_mode & 0o777) == "0o600"
    assert json.loads(yol.read_text(encoding="utf-8"))["port"] == 1234
