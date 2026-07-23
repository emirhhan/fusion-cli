"""Agent yardımcı katmanları: geçmiş, refleksiyon sezgiseli, denetim, sıkıştırma."""

from __future__ import annotations

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import compaction, history, reflexion, review

from .fakes import make_config


def _mesajlar():
    return [
        Message("system", "sistem"),
        Message("user", "ilk gorev"),
        Message("assistant", "", tool_calls=(ToolCall("1", "read_file", '{"path":"a"}'),)),
        Message("tool", "icerik", tool_call_id="1", name="read_file", ok=True),
        Message("assistant", "bitti"),
        Message("user", "ikinci gorev"),
        Message("assistant", "tamam"),
    ]


# --- Geçmiş ----------------------------------------------------------------- #


def test_kesme_noktasi_user_sinirina_kaydirilir():
    """Araç çağrısı ile sonucu asla ayrılmamalı; aksi halde sağlayıcı hata verir."""
    mesajlar = _mesajlar()

    kesim = history.safe_cut(mesajlar, keep_recent=5)

    assert mesajlar[kesim].role == "user"


def test_guvenli_kesim_yoksa_sifir_doner():
    mesajlar = [Message("assistant", "a"), Message("tool", "b", tool_call_id="1")]

    assert history.safe_cut(mesajlar, keep_recent=1) == 0


def test_esik_altinda_sikistirma_gerekmez():
    assert not history.needs_compression([Message("user", "kisa")])


def test_esik_ustunde_sikistirma_gerekir():
    buyuk = [Message("user", "x" * (history.COMPRESS_THRESHOLD_CHARS + 1))]

    assert history.needs_compression(buyuk)


def test_iz_arac_cagrilarini_ve_sonuclarini_korur():
    iz = history.transcript(_mesajlar())

    assert "[araç çağrısı] read_file" in iz
    assert "[sonuç read_file]" in iz
    assert "[kullanıcı] ilk gorev" in iz


def test_iz_hatali_sonuclari_isaretler():
    iz = history.transcript([Message("tool", "Dosya yok: a.txt", name="read_file", ok=False)])

    assert "⟵ HATA" in iz


# --- Yarım kalma sezgiseli --------------------------------------------------- #


def test_tamamlanmamis_todo_isi_yarim_yapar():
    assert reflexion.looks_unfinished("bitti", tool_calls_last_turn=0, has_pending_todos=True)


def test_arac_sonrasi_kisa_cevap_yarim_sayilir():
    assert reflexion.looks_unfinished("bak", tool_calls_last_turn=2, has_pending_todos=False)


def test_kod_iceren_kisa_cevap_yarim_sayilmaz():
    assert not reflexion.looks_unfinished(
        "`x = 1`", tool_calls_last_turn=2, has_pending_todos=False
    )


def test_uzun_cevap_yarim_sayilmaz():
    assert not reflexion.looks_unfinished(
        "u" * 100, tool_calls_last_turn=2, has_pending_todos=False
    )


def test_arac_cagrilmadiysa_kisa_cevap_yarim_sayilmaz():
    assert not reflexion.looks_unfinished("evet", tool_calls_last_turn=0, has_pending_todos=False)


def test_israrci_not_farkli_metin_kullanir():
    assert reflexion.note(persistent=True).content != reflexion.note(persistent=False).content


# --- Öz-denetim çıktısı ------------------------------------------------------ #


def test_tamam_cevabi_sorun_yok_demektir():
    assert review.parse_feedback("TAMAM") == ""


def test_tamam_ile_baslayan_cevap_da_temiz_sayilir():
    assert review.parse_feedback("TAMAM, her şey yolunda.") == ""


def test_bos_cevap_temiz_sayilir():
    assert review.parse_feedback("   ") == ""


def test_cok_kisa_cevap_talimat_sayilmaz():
    assert review.parse_feedback("hmm") == ""


def test_somut_talimat_dondurulur():
    talimat = "Testleri çalıştırmadın, önce pytest koş."

    assert review.parse_feedback(talimat) == talimat


# --- Sıkıştırma -------------------------------------------------------------- #


async def test_esik_altinda_gecmise_dokunulmaz():
    mesajlar = [Message("user", "kisa")]

    assert await compaction.compress(mesajlar, config=make_config()) is mesajlar


async def test_ozet_uretilemezse_gecmis_degismez(monkeypatch):
    async def _bos(trace, config):
        return ""

    monkeypatch.setattr(compaction, "_summarize", _bos)
    mesajlar = [
        Message("user", "x" * 30_000),
        Message("assistant", "a"),
        Message("user", "b"),
        Message("assistant", "c"),
        Message("user", "d"),
        Message("assistant", "e"),
        Message("user", "f"),
    ]

    assert await compaction.compress(mesajlar, config=make_config()) == mesajlar


async def test_ozet_uretilirse_eski_turlar_tek_nota_iner(monkeypatch):
    async def _ozet(trace, config):
        return "kisa ozet"

    monkeypatch.setattr(compaction, "_summarize", _ozet)
    mesajlar = [Message("user", "x" * 30_000)] + [
        Message("user" if i % 2 == 0 else "assistant", f"m{i}") for i in range(8)
    ]

    sonuc = await compaction.compress(mesajlar, config=make_config())

    assert len(sonuc) < len(mesajlar)
    assert sonuc[0].content.startswith("[önceki konuşmanın özeti]")


def test_dosya_satir_referansi_somut_teslim_sayilir():
    """Kısa ama tam bir cevap ("src/app.py:42") yarım sanılıp tekrarlatılmamalı."""
    assert not reflexion.looks_unfinished(
        "src/fusion_cli/observability/bus.py:24",
        tool_calls_last_turn=2,
        has_pending_todos=False,
    )


def test_dosya_yolu_iceren_kisa_cevap_somut_sayilir():
    assert not reflexion.looks_unfinished(
        "Tanım src/core/events.py dosyasında.",
        tool_calls_last_turn=1,
        has_pending_todos=False,
    )


def test_somut_isaret_tasimayan_kisa_cevap_hala_yarim():
    assert reflexion.looks_unfinished("bakiyorum", tool_calls_last_turn=1, has_pending_todos=False)
