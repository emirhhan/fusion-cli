"""Sürücü süreyi payload'da taşır, farklı sürecin timestamp'ini göndermez."""

from __future__ import annotations

import argparse
import sys

from evals import live_drive

_FAKE_CORE = """
import json, sys
for line in sys.stdin:
    request=json.loads(line)
    payload={'ok':True}
    if request['ad']=='tur.calistir':
        payload={'ok':request['veri'].get('sure_s')==5,
                 'metin':json.dumps(sorted(request['veri']))}
    print(json.dumps({'tip':'sonuc','id':request['id'],'veri':payload}),flush=True)
"""


async def test_driver_propagates_only_duration_to_turn_request(tmp_path, monkeypatch):
    monkeypatch.setattr(live_drive, "_komut", lambda args: [sys.executable, "-c", _FAKE_CORE])
    args = argparse.Namespace(
        kok=str(tmp_path), mod="auto", gorev=["merhaba"], sure=5, chrome="", onay="once"
    )
    result = await live_drive.drive(args, None)
    assert result["turlar"][0]["ok"]
    assert result["turlar"][0]["metin"] == '["gorev", "sure_s"]'
