"""Köke bağlı descriptor okumasının yarış, tür ve boyut sınırları."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest


def _reader():
    from fusion_cli.core.source_read import read_scoped_source

    return read_scoped_source


def _open_hook(monkeypatch, replacement):
    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {replacement})
    monkeypatch.setattr(os, "open", replacement)


def test_normal_kaynak_baytlari_ayni_descriptor_uzerinden_okunur(tmp_path):
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    payload = "def örnek():\n    return 1\n".encode()
    source.write_bytes(payload)
    assert _reader()(tmp_path, Path("src/sample.py"), max_bytes=len(payload)) == payload


@pytest.mark.parametrize("relative", [Path("../outside.py"), Path(), Path("/absolute.py")])
def test_gecersiz_goreli_yol_descriptor_acilmadan_reddedilir(tmp_path, monkeypatch, relative):
    def forbidden_open(*args, **kwargs):
        pytest.fail("Geçersiz göreli yolda descriptor açılmamalı.")

    _open_hook(monkeypatch, forbidden_open)
    assert _reader()(tmp_path, relative, max_bytes=20) is None


def test_kok_traversal_iceriyorsa_descriptor_acilmadan_reddedilir(tmp_path, monkeypatch):
    def forbidden_open(*args, **kwargs):
        pytest.fail("Geçersiz kökte descriptor açılmamalı.")

    _open_hook(monkeypatch, forbidden_open)
    assert _reader()(tmp_path / ".." / "project", Path("sample.py"), max_bytes=20) is None


@pytest.mark.parametrize("component", ["leaf", "parent", "root"])
def test_acma_anindaki_symlink_degisimi_yasak_bayt_okumaz(tmp_path, monkeypatch, component):
    root = tmp_path / "project"
    source = root / "src" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"allowed")
    excluded = tmp_path / "excluded"
    excluded.mkdir()
    (excluded / "sample.py").write_bytes(b"forbidden")
    real_open = os.open
    read_calls = []
    was_swapped = False
    names = {"leaf": "sample.py", "parent": "src", "root": "project"}

    def swap_before_open(path, flags, *args, **kwargs):
        nonlocal was_swapped
        if str(path) == names[component] and not was_swapped:
            was_swapped = True
            if component == "leaf":
                source.unlink()
                source.symlink_to(excluded / "sample.py")
            else:
                target = source.parent if component == "parent" else root
                target.rename(tmp_path / "original")
                target.symlink_to(excluded, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    _open_hook(monkeypatch, swap_before_open)
    real_read = os.read

    def record_read(descriptor, count):
        read_calls.append(descriptor)
        return real_read(descriptor, count)

    monkeypatch.setattr(os, "read", record_read)
    assert _reader()(root, Path("src/sample.py"), max_bytes=20) is None
    assert was_swapped
    assert read_calls == []


@pytest.mark.parametrize("mutation", ["growth", "same_size_change"])
def test_okuma_sirasinda_degisen_kaynak_donmez_ve_bayt_tavani_asmaz(
    tmp_path, monkeypatch, mutation
):
    source = tmp_path / "sample.py"
    source.write_bytes(b"abc")
    before = source.stat()
    real_read = os.read
    counts = []
    was_changed = False

    def change_after_read(descriptor, count):
        nonlocal was_changed
        payload = real_read(descriptor, count)
        counts.append(len(payload))
        if not was_changed:
            was_changed = True
            source.write_bytes(b"x" * 100 if mutation == "growth" else b"xyz")
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        return payload

    monkeypatch.setattr(os, "read", change_after_read)
    assert _reader()(tmp_path, Path("sample.py"), max_bytes=10) is None
    assert was_changed and sum(counts) <= 11


def test_buyuk_dosya_icerik_okumadan_reddedilir(tmp_path, monkeypatch):
    (tmp_path / "sample.py").write_bytes(b"x" * 11)

    def forbidden_read(*args, **kwargs):
        pytest.fail("Büyük dosyanın içeriği okunmamalı.")

    monkeypatch.setattr(os, "read", forbidden_read)
    assert _reader()(tmp_path, Path("sample.py"), max_bytes=10) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO bu platformda yok")
def test_fifo_bloklamadan_ve_icerik_okumadan_reddedilir(tmp_path, monkeypatch):
    fifo = tmp_path / "source.py"
    os.mkfifo(fifo)

    def forbidden_read(*args, **kwargs):
        pytest.fail("FIFO içeriği okunmamalı.")

    monkeypatch.setattr(os, "read", forbidden_read)
    result = []
    reader = threading.Thread(
        target=lambda: result.append(_reader()(tmp_path, Path("source.py"), max_bytes=20)),
        daemon=True,
    )
    reader.start()
    reader.join(1)
    try:
        assert not reader.is_alive(), "FIFO açılışı bloklanmamalı."
        assert result == [None]
    finally:
        if reader.is_alive():
            writer = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(writer)
            reader.join(1)


def test_desteklenmeyen_platformda_kaynak_acilmadan_vazgecilir(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "supports_dir_fd", set())

    def forbidden_open(*args, **kwargs):
        pytest.fail("Desteklenmeyen platformda dosya açılmamalı.")

    monkeypatch.setattr(os, "open", forbidden_open)
    assert _reader()(tmp_path, Path("sample.py"), max_bytes=20) is None
