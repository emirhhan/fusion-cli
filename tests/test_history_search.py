"""Geçmiş oturumlarında sınırlı içerik araması.

Bu sınıfın varlık nedeni gerçek bir kabul hatasıdır: paketli uygulamada eski bir
`game` sohbeti aranınca "konuşma bulunamadı" döndü. Sebep veri kaybı değildi —
arama yalnızca YÜKLENMİŞ sayfaların BAŞLIKLARINDA çalışıyordu ve Claude
kaynağındaki oturumların hiçbirinde `ai-title` kaydı yoktur. Bu testler aramanın
başlığa değil içeriğe, sayfaya değil kaynağa baktığını sabitler.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fusion_cli.history.models import SessionRef, Turn
from fusion_cli.history.search import search_sessions


@dataclass
class _FakeSource:
    """Başlığı içerikten bağımsız olan bir kaynak — gerçek Claude deposu gibi."""

    name: str = "claude"
    #: session_id -> turlar
    icerik: dict[str, tuple[Turn, ...]] | None = None
    #: `read` kaç kez çağrıldı; sınırların gerçekten kestiğini ölçer.
    okuma_sayisi: int = 0

    def __post_init__(self) -> None:
        if self.icerik is None:
            self.icerik = {
                "s1": (
                    Turn("user", "bana bir oyun yaz", 1.0),
                    Turn("assistant", "tabii, game loop kuruyorum", 2.0),
                ),
                "s2": (
                    Turn("user", "fatura tablosu lazım", 3.0),
                    Turn("assistant", "hazırlıyorum", 4.0),
                ),
            }

    def is_installed(self) -> bool:
        return True

    def list(self, root=None, limit=None):
        del root
        refs = tuple(
            SessionRef("claude", sid, f"2026-09-01 · {i * 10} bayt", float(100 - i))
            for i, sid in enumerate(sorted(self.icerik or {}))
        )
        return refs if limit is None else refs[:limit]

    def list_for_root(self, root, limit=None):
        return self.list(root, limit)

    def read(self, session_id, cursor=0, limit=50):
        self.okuma_sayisi += 1
        turns = (self.icerik or {}).get(session_id, ())
        return turns[cursor : cursor + limit]


def test_baslikta_gecmeyen_kelime_icerikte_bulunur():
    source = _FakeSource()

    sonuc = search_sessions(source, "game")

    assert [eslesme.ref.session_id for eslesme in sonuc.matches] == ["s1"]
    assert sonuc.matches[0].in_title is False
    assert "game" in sonuc.matches[0].snippet


def test_baslik_eslesmesi_dosya_okumadan_bulunur():
    source = _FakeSource()

    sonuc = search_sessions(source, "2026-09-01")

    assert len(sonuc.matches) == 2
    assert all(eslesme.in_title for eslesme in sonuc.matches)
    assert source.okuma_sayisi == 0


def test_turkce_buyuk_kucuk_harf_farki_eslesmeyi_bozmaz():
    source = _FakeSource(icerik={"s1": (Turn("user", "IŞIK açıldı", 1.0),)})

    assert search_sessions(source, "ışık").matches
    assert search_sessions(source, "IŞIK").matches
    assert search_sessions(source, "işik").matches == ()


def test_bos_sorgu_hicbir_kaynagi_taramaz():
    source = _FakeSource()

    sonuc = search_sessions(source, "   ")

    assert sonuc.matches == ()
    assert sonuc.scanned == 0
    assert source.okuma_sayisi == 0


def test_snippet_sirlari_maskeler():
    source = _FakeSource(
        icerik={"s1": (Turn("user", "anahtar OPENAI_API_KEY=sk-12345678901234567890", 1.0),)}
    )

    sonuc = search_sessions(source, "anahtar")

    assert "12345678901234567890" not in sonuc.matches[0].snippet


def test_tarama_oturum_sinirinda_kismi_sonuc_dondurur():
    icerik = {f"s{i}": (Turn("user", "oyun", 1.0),) for i in range(10)}
    source = _FakeSource(icerik=icerik)

    sonuc = search_sessions(source, "oyun", scan_limit=3)

    assert sonuc.scanned == 3
    assert sonuc.partial is True
    assert sonuc.reason


def test_sonuc_sayisi_limitle_kirpilir():
    icerik = {f"s{i}": (Turn("user", "oyun", 1.0),) for i in range(10)}
    source = _FakeSource(icerik=icerik)

    sonuc = search_sessions(source, "oyun", limit=2)

    assert len(sonuc.matches) == 2
    assert sonuc.partial is True


def test_sure_asiminda_tarama_durur_ve_kismi_isaretlenir():
    icerik = {f"s{i}": (Turn("user", "oyun", 1.0),) for i in range(10)}
    source = _FakeSource(icerik=icerik)
    # Her okumada saat 1 saniye ilerler; 2 saniyelik bütçe birkaç oturumda dolar.
    sayac = iter(range(0, 100))

    sonuc = search_sessions(source, "oyun", deadline_s=2.0, monotonic=lambda: float(next(sayac)))

    assert sonuc.partial is True
    assert sonuc.scanned < 10


def test_bozuk_kaynak_istisnasi_aramayi_dusurmez():
    class _BozukSource(_FakeSource):
        def read(self, session_id, cursor=0, limit=50):
            raise OSError("okunamadı")

    sonuc = search_sessions(_BozukSource(), "game")

    assert sonuc.matches == ()
    assert sonuc.scanned == 2


@pytest.mark.parametrize("gecersiz", [0, -1])
def test_gecersiz_limit_reddedilir(gecersiz):
    with pytest.raises(ValueError):
        search_sessions(_FakeSource(), "oyun", limit=gecersiz)
