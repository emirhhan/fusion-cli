"""Masaüstü uygulamasının geçmiş keşif ve sürdürme protokolü."""

from __future__ import annotations

import json
from dataclasses import dataclass

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.history.models import SessionRef, Turn


@dataclass
class _FakeSource:
    name: str = "claude"

    def is_installed(self) -> bool:
        return True

    def list(self, root=None, limit=None):
        del root
        refs = (
            SessionRef("claude", "s1", "İlk sohbet", 20.0, turn_count=3, size_bytes=120),
            SessionRef("claude", "s2", "İkinci sohbet", 10.0, turn_count=1, size_bytes=40),
        )
        return refs if limit is None else refs[:limit]

    def list_for_root(self, root, limit=None):
        return self.list(root, limit)

    def read(self, session_id, cursor=0, limit=50):
        assert session_id in {"s1", "s2"}
        turns = (
            Turn("user", "oyun yap", 1.0),
            Turn("assistant", "hazırlıyorum", 2.0),
            Turn("user", "OPENAI_API_KEY=12345678901234567890", 3.0),
        )
        return turns[cursor : cursor + limit]


def _result(lines: list[str], identifier: str):
    for line in reversed(lines):
        payload = json.loads(line)
        if payload.get("tip") == "sonuc" and payload.get("id") == identifier:
            return payload["veri"]
    raise AssertionError(identifier)


def _patch_source(monkeypatch, source):
    monkeypatch.setattr("fusion_cli.appserver.history.available_sources", lambda _home: (source,))
    monkeypatch.setattr(
        "fusion_cli.appserver.history.source_by_name",
        lambda _home, name: source if name == source.name else None,
    )


async def test_gecmis_kaynaklar_yalniz_kurulu_kaynaklari_dondurur(tmp_path, monkeypatch):
    source = _FakeSource()
    _patch_source(monkeypatch, source)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")

    await session.handle(Request("1", "gecmis.kaynaklar", {}))

    assert _result(lines, "1") == {
        "ok": True,
        "kaynaklar": [{"ad": "claude", "komut": "/resumeclaude"}],
    }


async def test_gecmis_oturumlar_sayfali_kunye_dondurur(tmp_path, monkeypatch):
    _patch_source(monkeypatch, _FakeSource())
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")

    await session.handle(
        Request("2", "gecmis.oturumlar", {"kaynak": "claude", "cursor": 0, "limit": 1})
    )

    result = _result(lines, "2")
    assert result["ok"] is True
    assert result["oturumlar"][0]["oturum_id"] == "s1"
    assert result["oturumlar"][0]["baslik"] == "İlk sohbet"
    assert result["next_cursor"] == 1
    assert result["has_more"] is True


async def test_gecmis_onizle_turlari_sayfali_dondurur(tmp_path, monkeypatch):
    _patch_source(monkeypatch, _FakeSource())
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")

    await session.handle(
        Request(
            "3",
            "gecmis.onizle",
            {"kaynak": "claude", "oturum_id": "s1", "cursor": 0, "limit": 2},
        )
    )

    result = _result(lines, "3")
    assert [turn["rol"] for turn in result["turlar"]] == ["user", "assistant"]
    assert result["next_cursor"] == 2
    assert result["has_more"] is True


async def test_gecmis_surdur_kunyeyi_bekletir_ve_sir_sayisini_dondurur(tmp_path, monkeypatch):
    _patch_source(monkeypatch, _FakeSource())
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")

    await session.handle(Request("4", "gecmis.surdur", {"kaynak": "claude", "oturum_id": "s1"}))

    result = _result(lines, "4")
    assert result["ok"] is True
    assert result["kaynak"] == "claude"
    assert result["baslik"] == "İlk sohbet"
    assert result["sir_sayisi"] == 1
    assert session._state.pending_digest is not None
    assert "İlk sohbet" in session._state.pending_digest


async def test_kurulu_olmayan_kaynak_anlasilir_hata_doner(tmp_path, monkeypatch):
    monkeypatch.setattr("fusion_cli.appserver.history.source_by_name", lambda *_args: None)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")

    await session.handle(Request("5", "gecmis.oturumlar", {"kaynak": "hermes"}))

    result = _result(lines, "5")
    assert result["ok"] is False
    assert "bulunamadı" in result["metin"]
