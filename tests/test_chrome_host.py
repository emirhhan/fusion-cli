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
    yol = Path("/Users/motogate/Desktop/01-Projeler/fusion-cli/chrome-extension")
    assert chrome_host.extension_id_for_path(yol) == "gifkppllofppjplfhapngpjhbplapnpc"


def test_yuklu_fusion_browser_kimligi_profil_ayarlarindan_bulunur(tmp_path):
    profil = tmp_path / "Library/Application Support/Google/Chrome/Default"
    profil.mkdir(parents=True)
    (profil / "Preferences").write_text(
        json.dumps(
            {
                "extensions": {
                    "settings": {
                        "abc": {"manifest": {"name": "Fusion Browser"}},
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
