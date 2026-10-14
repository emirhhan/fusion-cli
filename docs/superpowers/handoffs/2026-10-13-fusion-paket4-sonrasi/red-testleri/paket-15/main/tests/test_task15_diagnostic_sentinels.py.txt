"""Teşhis hazırlığı: yalnız sentetik metin, dosya okumayan public redactor."""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from fusion_cli.core.redaction import REDACTED_MARK, redact


@pytest.fixture
def unread_env_guard(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Hariç tutulan env dosyası okunmaya çalışılırsa fixture hemen kırılır."""
    attempts: list[str] = []
    original_open = builtins.open
    original_path_open = Path.open

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file).name == ".env":
            attempts.append("env")
            raise AssertionError("Hariç tutulan env dosyası okunamaz.")
        return original_open(file, *args, **kwargs)

    def guarded_path_open(path, *args, **kwargs):
        if path.name == ".env":
            attempts.append("env")
            raise AssertionError("Hariç tutulan env dosyası okunamaz.")
        return original_path_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    return attempts


def test_bearer_sentinel_is_removed_without_reading_env(unread_env_guard: list[str]) -> None:
    sentinel = "TASK15_FAKE_BEARER_SENTINEL"
    result = redact(f"durum=offline Authorization: Bearer {sentinel}")
    assert unread_env_guard == []
    assert sentinel not in result
    assert REDACTED_MARK in result
    assert "durum=offline" in result


def test_multiline_private_key_body_is_removed_without_reading_env(
    unread_env_guard: list[str],
) -> None:
    sentinel = "TASK15_FAKE_PEM_BODY_SENTINEL"
    result = redact(
        f"durum=offline\n-----BEGIN PRIVATE KEY-----\n{sentinel}\n"
        "-----END PRIVATE KEY-----\nhata=offline"
    )
    assert unread_env_guard == []
    assert sentinel not in result
    assert REDACTED_MARK in result
    assert "hata=offline" in result
