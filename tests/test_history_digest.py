"""Oturum künyesi ve sır sayımı."""

from __future__ import annotations

from fusion_cli.history.digest import build_digest, count_secrets
from fusion_cli.history.models import SessionRef, Turn


class _SahteKaynak:
    name = "claude"

    def __init__(self, turlar):
        self._turlar = turlar

    def is_installed(self):
        return True

    def list(self, root=None):
        return ()

    def read(self, session_id, cursor=0, limit=50):
        return tuple(self._turlar[cursor : cursor + limit])


def _ref():
    return SessionRef(source="claude", session_id="s1", title="Test", updated_at=0.0, turn_count=2)


def test_kunye_kullanici_mesajlarini_listeler():
    kaynak = _SahteKaynak(
        [Turn("user", "ilk istek"), Turn("assistant", "cevap"), Turn("user", "ikinci istek")]
    )

    digest = build_digest(kaynak, _ref())

    assert "ilk istek" in digest.text
    assert "ikinci istek" in digest.text


def test_kunye_ajan_cevaplarini_listelemez():
    kaynak = _SahteKaynak([Turn("user", "istek"), Turn("assistant", "uzun ajan cevabı")])

    digest = build_digest(kaynak, _ref())

    assert "uzun ajan cevabı" not in digest.text


def test_kunye_deterministik():
    kaynak = _SahteKaynak([Turn("user", "a"), Turn("user", "b")])

    assert build_digest(kaynak, _ref()).text == build_digest(kaynak, _ref()).text


def test_sir_sayilir_ama_maskelenmez():
    kaynak = _SahteKaynak([Turn("user", "ANTHROPIC_API_KEY=sk-ant-0123456789abcdefghij")])

    digest = build_digest(kaynak, _ref())

    assert digest.secret_count >= 1
    assert "sk-ant-0123456789abcdefghij" in digest.text


def test_sirsiz_metinde_sayim_sifir():
    assert count_secrets("burada hiçbir şey yok") == 0


def test_bilinen_desenler_sayilir():
    assert count_secrets("Bearer abcdefghijklmnopqrstuvwx") >= 1
    assert count_secrets("DB_PASSWORD=cokgizli123") >= 1
