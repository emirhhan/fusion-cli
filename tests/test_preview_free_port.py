"""Önizleme portu "bağlanılamıyor" diye değil, gerçekten bağlanabiliyorsa boş sayılır.

Ölçüldü (28 Ekim): macOS `sharingd` (AirDrop/AirPlay) 8770'i IPv6 üzerinde dinlemeye
başladı. `free_port` 127.0.0.1'e bağlanmayı deneyip reddedilince portu boş sandı,
sunucu bind'de `Address already in use` ile düştü ve bütün site önizlemeleri bozuldu.
"""

from __future__ import annotations

import socket

from fusion_cli.tools import preview_server


def test_bind_edilemeyen_port_bos_sayilmaz(monkeypatch):
    tutulan = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tutulan.bind(("127.0.0.1", 0))  # dinlemiyor: bağlantı reddedilir ama port dolu
    port = tutulan.getsockname()[1]
    monkeypatch.setattr(preview_server, "PREVIEW_PORT_START", port)
    monkeypatch.setattr(preview_server, "PREVIEW_PORT_SPAN", 1)
    try:
        secilen = preview_server.free_port()
    finally:
        tutulan.close()

    assert secilen != port


def test_bos_port_tercih_araligindan_secilir(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(preview_server, "PREVIEW_PORT_START", port)
    monkeypatch.setattr(preview_server, "PREVIEW_PORT_SPAN", 1)

    assert preview_server.free_port() == port
